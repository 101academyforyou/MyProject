import csv
import io
import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request

from crm.server import create_server


class ApiTest(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.server = create_server(self.db_path, "127.0.0.1", 0)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.server.db.close()
        os.remove(self.db_path)

    def call(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method)
        if data:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req) as res:
                return res.status, json.loads(res.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def create(self, **fields):
        fields.setdefault("name", "王小明")
        status, body = self.call("POST", "/api/customers", fields)
        self.assertEqual(status, 201, body)
        return body

    def test_customer_crud(self):
        c = self.create(company="大明科技", email="ming@example.com", phone="0912345678")
        self.assertEqual(c["status"], "潛在客戶")

        status, got = self.call("GET", f"/api/customers/{c['id']}")
        self.assertEqual((status, got["company"]), (200, "大明科技"))

        status, upd = self.call("PUT", f"/api/customers/{c['id']}", {"status": "洽談中"})
        self.assertEqual((status, upd["status"], upd["name"]), (200, "洽談中", "王小明"))

        status, _ = self.call("DELETE", f"/api/customers/{c['id']}")
        self.assertEqual(status, 200)
        status, _ = self.call("GET", f"/api/customers/{c['id']}")
        self.assertEqual(status, 404)

    def test_validation(self):
        status, body = self.call("POST", "/api/customers", {"name": "  "})
        self.assertEqual(status, 400)
        self.assertIn("必填", body["error"])
        status, _ = self.call("POST", "/api/customers", {"name": "A", "status": "不存在"})
        self.assertEqual(status, 400)
        status, _ = self.call("POST", "/api/customers", {"name": "A", "email": "bad"})
        self.assertEqual(status, 400)
        status, _ = self.call("PUT", "/api/customers/999", {"name": "X"})
        self.assertEqual(status, 404)

    def test_search_and_filter(self):
        self.create(name="王小明", company="大明科技")
        self.create(name="李美華", company="美華貿易", status="已成交")
        self.create(name="陳大同", notes="介紹人：大明", status="已成交")

        _, rows = self.call("GET", "/api/customers?q=" + urllib.parse.quote("大明"))
        self.assertEqual({r["name"] for r in rows}, {"王小明", "陳大同"})

        _, rows = self.call("GET", "/api/customers?status=" + urllib.parse.quote("已成交"))
        self.assertEqual({r["name"] for r in rows}, {"李美華", "陳大同"})

        _, meta = self.call("GET", "/api/meta")
        self.assertEqual(meta["summary"]["已成交"], 2)
        self.assertEqual(meta["summary"]["潛在客戶"], 1)

    def export(self, query=""):
        with urllib.request.urlopen(self.base + "/api/customers/export.csv?" + query) as res:
            self.assertEqual(res.status, 200)
            self.assertTrue(res.headers["Content-Type"].startswith("text/csv"))
            self.assertIn("attachment", res.headers["Content-Disposition"])
            raw = res.read()
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"), "應包含 UTF-8 BOM 供 Excel 辨識")
        return list(csv.reader(io.StringIO(raw.decode("utf-8-sig"))))

    def test_export_csv(self):
        a = self.create(name="王小明", company="大明科技", email="ming@example.com",
                        notes="第一行\n第二行, 含逗號與\"引號\"")
        self.create(name="李美華", company="美華貿易", status="已成交")
        self.call("POST", f"/api/customers/{a['id']}/interactions",
                  {"contact_date": "2026-09-15", "content": "x"})

        rows = self.export()
        header = rows[0]
        self.assertEqual(header[:3], ["編號", "客戶名稱", "公司"])
        self.assertEqual(len(rows), 3)
        ming = dict(zip(header, next(r for r in rows[1:] if r[1] == "王小明")))
        self.assertEqual(ming["Email"], "ming@example.com")
        self.assertEqual(ming["備註"], "第一行\n第二行, 含逗號與\"引號\"")
        self.assertEqual(ming["聯絡紀錄筆數"], "1")
        self.assertEqual(ming["最後聯絡日期"], "2026-09-15")

    def test_export_csv_uses_search_and_filter(self):
        self.create(name="王小明", company="大明科技")
        self.create(name="李美華", company="美華貿易", status="已成交")
        self.create(name="陳大同", notes="大明介紹", status="已成交")

        rows = self.export("q=" + urllib.parse.quote("大明"))
        self.assertEqual({r[1] for r in rows[1:]}, {"王小明", "陳大同"})
        rows = self.export("status=" + urllib.parse.quote("已成交"))
        self.assertEqual({r[1] for r in rows[1:]}, {"李美華", "陳大同"})
        rows = self.export("q=" + urllib.parse.quote("大明") + "&status="
                           + urllib.parse.quote("已成交"))
        self.assertEqual([r[1] for r in rows[1:]], ["陳大同"])
        # 沒有符合的資料時仍輸出標題列
        rows = self.export("q=nobody")
        self.assertEqual(len(rows), 1)

    def test_export_csv_escapes_formulas(self):
        self.create(name="=HYPERLINK(\"http://evil\")", phone="+886 912 345 678",
                    notes="@SUM(A1)")
        row = dict(zip(*self.export()[:2]))
        self.assertEqual(row["客戶名稱"], "'=HYPERLINK(\"http://evil\")")
        self.assertEqual(row["電話"], "'+886 912 345 678")
        self.assertEqual(row["備註"], "'@SUM(A1)")

    def test_interactions(self):
        c = self.create()
        path = f"/api/customers/{c['id']}/interactions"
        status, i1 = self.call("POST", path, {
            "contact_date": "2026-09-01", "method": "電話", "content": "初次聯繫"})
        self.assertEqual(status, 201)
        self.call("POST", path, {"contact_date": "2026-09-15", "method": "會議", "content": "報價"})

        _, items = self.call("GET", path)
        self.assertEqual([i["content"] for i in items], ["報價", "初次聯繫"])

        _, rows = self.call("GET", "/api/customers")
        self.assertEqual(rows[0]["interaction_count"], 2)
        self.assertEqual(rows[0]["last_contact"], "2026-09-15")

        status, upd = self.call("PUT", f"/api/interactions/{i1['id']}", {"content": "初次電話聯繫"})
        self.assertEqual((status, upd["content"]), (200, "初次電話聯繫"))

        status, _ = self.call("POST", path, {"content": ""})
        self.assertEqual(status, 400)
        status, _ = self.call("POST", path, {"content": "x", "contact_date": "昨天"})
        self.assertEqual(status, 400)
        status, _ = self.call("POST", "/api/customers/999/interactions", {"content": "x"})
        self.assertEqual(status, 404)

        self.call("DELETE", f"/api/interactions/{i1['id']}")
        _, items = self.call("GET", path)
        self.assertEqual(len(items), 1)

        # 刪除客戶時，聯絡紀錄一併刪除
        self.call("DELETE", f"/api/customers/{c['id']}")
        count = self.server.db.conn.execute("SELECT COUNT(*) FROM interactions").fetchone()[0]
        self.assertEqual(count, 0)

    def test_static_files(self):
        with urllib.request.urlopen(self.base + "/") as res:
            self.assertIn("客戶管理系統", res.read().decode())
        status, _ = self.call("GET", "/../../etc/passwd")
        self.assertEqual(status, 404)


if __name__ == "__main__":
    unittest.main()

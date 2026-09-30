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

    def test_interaction_filter_by_method(self):
        c = self.create()
        other = self.create(name="李美華")
        path = f"/api/customers/{c['id']}/interactions"
        for date, method, content in [("2026-09-01", "電話", "初次聯繫"),
                                      ("2026-09-10", "會議", "簡報"),
                                      ("2026-09-20", "電話", "追蹤報價")]:
            self.call("POST", path, {"contact_date": date, "method": method, "content": content})
        self.call("POST", f"/api/customers/{other['id']}/interactions",
                  {"method": "電話", "content": "別的客戶"})

        _, items = self.call("GET", path + "?method=" + urllib.parse.quote("電話"))
        self.assertEqual([i["content"] for i in items], ["追蹤報價", "初次聯繫"])
        _, items = self.call("GET", path + "?method=" + urllib.parse.quote("會議"))
        self.assertEqual([i["content"] for i in items], ["簡報"])
        _, items = self.call("GET", path + "?method=Email")
        self.assertEqual(items, [])

        # 未指定或空白時回傳全部
        _, items = self.call("GET", path)
        self.assertEqual(len(items), 3)
        _, items = self.call("GET", path + "?method=")
        self.assertEqual(len(items), 3)

        status, body = self.call("GET", path + "?method=" + urllib.parse.quote("飛鴿傳書"))
        self.assertEqual(status, 400)
        self.assertIn("聯絡方式", body["error"])
        status, _ = self.call("GET", "/api/customers/999/interactions?method=Email")
        self.assertEqual(status, 404)

    def test_static_files(self):
        with urllib.request.urlopen(self.base + "/") as res:
            self.assertIn("客戶管理系統", res.read().decode())
        status, _ = self.call("GET", "/../../etc/passwd")
        self.assertEqual(status, 404)


if __name__ == "__main__":
    unittest.main()

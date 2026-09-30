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

    def names(self, query):
        status, rows = self.call("GET", "/api/customers?" + query)
        self.assertEqual(status, 200, rows)
        return [r["name"] for r in rows]

    def test_sort(self):
        a = self.create(name="Alice", company="Zeta")
        b = self.create(name="Bob", company="")
        c = self.create(name="Carol", company="Alpha", status="已成交")
        for cust, date in [(a, "2026-09-10"), (c, "2026-09-20")]:
            self.call("POST", f"/api/customers/{cust['id']}/interactions",
                      {"contact_date": date, "content": "x"})

        self.assertEqual(self.names("sort=name"), ["Alice", "Bob", "Carol"])
        self.assertEqual(self.names("sort=name&order=desc"), ["Carol", "Bob", "Alice"])
        # 沒有公司名稱、從未聯絡的客戶，不論升冪或降冪都排在最後
        self.assertEqual(self.names("sort=company"), ["Carol", "Alice", "Bob"])
        self.assertEqual(self.names("sort=company&order=desc"), ["Alice", "Carol", "Bob"])
        self.assertEqual(self.names("sort=last_contact"), ["Alice", "Carol", "Bob"])
        self.assertEqual(self.names("sort=last_contact&order=desc"), ["Carol", "Alice", "Bob"])

        # 排序可與搜尋、篩選同時使用
        self.assertEqual(self.names("sort=name&order=desc&status="
                                    + urllib.parse.quote("潛在客戶")), ["Bob", "Alice"])

        # 未指定排序時維持原本的「最近更新優先」
        conn = self.server.db.conn
        for cust, ts in [(a, "2026-01-02"), (b, "2026-01-03"), (c, "2026-01-01")]:
            conn.execute("UPDATE customers SET updated_at = ? WHERE id = ?", (ts, cust["id"]))
        conn.commit()
        self.assertEqual(self.names(""), ["Bob", "Alice", "Carol"])

    def test_sort_validation(self):
        status, body = self.call("GET", "/api/customers?sort=email")
        self.assertEqual(status, 400)
        self.assertIn("排序欄位", body["error"])
        status, _ = self.call("GET", "/api/customers?sort=name&order=up")
        self.assertEqual(status, 400)

    def test_sort_boundaries(self):
        # 沒有任何客戶時排序回傳空陣列
        self.assertEqual(self.names("sort=name"), [])
        self.assertEqual(self.names("sort=last_contact&order=desc"), [])

        # 只有一位客戶
        self.create(name="Solo")
        self.assertEqual(self.names("sort=company&order=desc"), ["Solo"])

    def test_sort_ties_are_stable(self):
        # 排序值相同時，依建立順序（id）排列，升冪／降冪皆同
        ids = [self.create(name="同名", company="同公司")["id"] for _ in range(3)]
        for d in ids:
            self.call("POST", f"/api/customers/{d}/interactions",
                      {"contact_date": "2026-09-01", "content": "x"})
        for query in ["sort=name", "sort=name&order=desc", "sort=company&order=desc",
                      "sort=last_contact", "sort=last_contact&order=desc"]:
            _, rows = self.call("GET", "/api/customers?" + query)
            self.assertEqual([r["id"] for r in rows], ids, query)

    def test_sort_ignores_letter_case(self):
        # 區分大小寫時會變成 Alice, Carol, bob（大寫字母排在小寫之前）
        self.create(name="bob")
        self.create(name="Alice")
        self.create(name="Carol")
        self.assertEqual(self.names("sort=name"), ["Alice", "bob", "Carol"])
        self.assertEqual(self.names("sort=name&order=desc"), ["Carol", "bob", "Alice"])
        self.create(name="x", company="beta")
        self.create(name="y", company="Alpha")
        self.create(name="z", company="Gamma")
        self.assertEqual(self.names("sort=company")[:3], ["y", "x", "z"])

    def test_sort_last_contact_uses_latest_record(self):
        a = self.create(name="A")
        b = self.create(name="B")
        # A 最早與最晚的聯絡都有，排序應依最新一筆（09-30）而非第一筆
        for date in ["2026-01-01", "2026-09-30"]:
            self.call("POST", f"/api/customers/{a['id']}/interactions",
                      {"contact_date": date, "content": "x"})
        self.call("POST", f"/api/customers/{b['id']}/interactions",
                  {"contact_date": "2026-06-15", "content": "x"})
        self.assertEqual(self.names("sort=last_contact"), ["B", "A"])
        self.assertEqual(self.names("sort=last_contact&order=desc"), ["A", "B"])

    def test_sort_parameter_edge_cases(self):
        conn = self.server.db.conn
        for name, ts in [("Old", "2026-01-01"), ("New", "2026-02-01")]:
            c = self.create(name=name)
            conn.execute("UPDATE customers SET updated_at = ? WHERE id = ?", (ts, c["id"]))
        conn.commit()

        # 空白的 sort 視同未指定；未指定 sort 時 order 不影響預設排序
        self.assertEqual(self.names("sort="), ["New", "Old"])
        self.assertEqual(self.names("order=asc"), ["New", "Old"])
        # 排序方向不分大小寫
        self.assertEqual(self.names("sort=name&order=DESC"), ["Old", "New"])
        self.assertEqual(self.names("sort=name&order=Asc"), ["New", "Old"])
        # 空白的 order 使用預設升冪
        self.assertEqual(self.names("sort=name&order="), ["New", "Old"])

        # 排序欄位只接受白名單，無法注入 SQL
        for bad in ["name;DROP TABLE customers", "c.id", "NAME", "updated_at"]:
            status, _ = self.call("GET", "/api/customers?sort=" + urllib.parse.quote(bad))
            self.assertEqual(status, 400, bad)
        self.assertEqual(len(self.names("")), 2)

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

"""HTTP 伺服器：提供 REST API 與前端網頁。"""

import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from datetime import datetime
from urllib.parse import parse_qs, urlparse

from .db import CONTACT_METHODS, STATUSES, Database, ValidationError
from .export import customers_to_csv

STATIC_DIR = Path(__file__).parent / "static"
STATIC_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
}

# (method, 路徑正規式, 處理函式名稱)
ROUTES = [
    ("GET", r"/api/meta", "meta"),
    ("GET", r"/api/customers", "list_customers"),
    ("GET", r"/api/customers/export\.csv", "export_customers"),
    ("POST", r"/api/customers", "create_customer"),
    ("GET", r"/api/customers/(\d+)", "get_customer"),
    ("PUT", r"/api/customers/(\d+)", "update_customer"),
    ("DELETE", r"/api/customers/(\d+)", "delete_customer"),
    ("GET", r"/api/customers/(\d+)/interactions", "list_interactions"),
    ("POST", r"/api/customers/(\d+)/interactions", "create_interaction"),
    ("PUT", r"/api/interactions/(\d+)", "update_interaction"),
    ("DELETE", r"/api/interactions/(\d+)", "delete_interaction"),
]


class NotFound(Exception):
    pass


def make_handler(db):
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        server_version = "SimpleCRM/1.0"

        def log_message(self, fmt, *args):
            pass  # 保持終端機乾淨

        # ---------- 路由 ----------

        def _dispatch(self, method):
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/") or "/"
            self.query = {k: v[0] for k, v in parse_qs(parsed.query).items()}

            if method == "GET" and not path.startswith("/api/"):
                return self._serve_static(path)

            for m, pattern, name in ROUTES:
                match = re.fullmatch(pattern, path)
                if match and m == method:
                    args = [int(a) for a in match.groups()]
                    try:
                        with lock:
                            result = getattr(self, "api_" + name)(*args)
                        return self._respond(*result)
                    except ValidationError as e:
                        return self._json(400, {"error": str(e)})
                    except NotFound:
                        return self._json(404, {"error": "找不到資料"})
                    except json.JSONDecodeError:
                        return self._json(400, {"error": "JSON 格式錯誤"})
            self._json(404, {"error": "找不到路徑"})

        def do_GET(self):
            self._dispatch("GET")

        def do_POST(self):
            self._dispatch("POST")

        def do_PUT(self):
            self._dispatch("PUT")

        def do_DELETE(self):
            self._dispatch("DELETE")

        # ---------- 工具函式 ----------

        def _body(self):
            length = int(self.headers.get("Content-Length") or 0)
            if not length:
                return {}
            data = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(data, dict):
                raise ValidationError("請求內容必須是 JSON 物件")
            return data

        def _respond(self, status, body, headers=None):
            """body 為 bytes 時直接送出（需在 headers 指定 Content-Type），否則轉為 JSON。"""
            if headers is None:
                return self._json(status, body)
            self.send_response(status)
            for key, value in headers.items():
                self.send_header(key, value)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status, body):
            payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self._respond(
                status, payload, {"Content-Type": "application/json; charset=utf-8"}
            )

        def _serve_static(self, path):
            name = "index.html" if path == "/" else path.lstrip("/")
            file = (STATIC_DIR / name).resolve()
            if STATIC_DIR.resolve() not in file.parents or not file.is_file():
                return self._json(404, {"error": "找不到檔案"})
            data = file.read_bytes()
            self.send_response(200)
            self.send_header(
                "Content-Type", STATIC_TYPES.get(file.suffix, "application/octet-stream")
            )
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        @staticmethod
        def _found(obj):
            if obj is None:
                raise NotFound()
            return obj

        # ---------- API ----------

        def api_meta(self):
            return 200, {
                "statuses": STATUSES,
                "contact_methods": CONTACT_METHODS,
                "summary": db.status_summary(),
            }

        def _customer_filters(self):
            """列表與匯出共用的搜尋／篩選條件。"""
            return {
                "q": self.query.get("q", ""),
                "status": self.query.get("status", ""),
            }

        def api_list_customers(self):
            return 200, db.list_customers(**self._customer_filters())

        def api_export_customers(self):
            filename = f"customers-{datetime.now():%Y%m%d-%H%M%S}.csv"
            return 200, customers_to_csv(db.list_customers(**self._customer_filters())), {
                "Content-Type": "text/csv; charset=utf-8",
                "Content-Disposition": f'attachment; filename="{filename}"',
            }

        def api_create_customer(self):
            return 201, db.create_customer(self._body())

        def api_get_customer(self, cid):
            return 200, self._found(db.get_customer(cid))

        def api_update_customer(self, cid):
            return 200, self._found(db.update_customer(cid, self._body()))

        def api_delete_customer(self, cid):
            if not db.delete_customer(cid):
                raise NotFound()
            return 200, {"ok": True}

        def api_list_interactions(self, cid):
            self._found(db.get_customer(cid))
            return 200, db.list_interactions(cid)

        def api_create_interaction(self, cid):
            return 201, self._found(db.create_interaction(cid, self._body()))

        def api_update_interaction(self, iid):
            return 200, self._found(db.update_interaction(iid, self._body()))

        def api_delete_interaction(self, iid):
            if not db.delete_interaction(iid):
                raise NotFound()
            return 200, {"ok": True}

    return Handler


def create_server(db_path="crm.db", host="127.0.0.1", port=8000):
    db = Database(db_path)
    server = ThreadingHTTPServer((host, port), make_handler(db))
    server.db = db
    return server

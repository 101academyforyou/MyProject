"""資料庫層：使用 SQLite 儲存客戶與聯絡紀錄。"""

import sqlite3
from datetime import datetime

STATUSES = ["潛在客戶", "洽談中", "已成交", "暫停", "流失"]
CONTACT_METHODS = ["電話", "Email", "會議", "拜訪", "通訊軟體", "其他"]

CUSTOMER_FIELDS = ["name", "company", "email", "phone", "address", "status", "notes"]
INTERACTION_FIELDS = ["contact_date", "method", "content"]

# 客戶列表可用的排序欄位（API 參數 → SQL 欄位）
SORT_FIELDS = {"name": "c.name", "company": "c.company", "last_contact": "last_contact"}
SORT_ORDERS = ["asc", "desc"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS customers (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    company     TEXT NOT NULL DEFAULT '',
    email       TEXT NOT NULL DEFAULT '',
    phone       TEXT NOT NULL DEFAULT '',
    address     TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT '潛在客戶',
    notes       TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS interactions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id  INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    contact_date TEXT NOT NULL,
    method       TEXT NOT NULL DEFAULT '其他',
    content      TEXT NOT NULL,
    created_at   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_interactions_customer ON interactions(customer_id);
"""


class ValidationError(ValueError):
    pass


def _now():
    return datetime.now().isoformat(timespec="seconds")


def _clean(data, fields):
    """只保留允許的欄位，並將值轉為去除前後空白的字串。"""
    out = {}
    for f in fields:
        if f in data and data[f] is not None:
            out[f] = str(data[f]).strip()
    return out


class Database:
    def __init__(self, path):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self):
        self.conn.close()

    # ---------- 客戶 ----------

    def _validate_customer(self, data, partial=False):
        if not partial or "name" in data:
            if not data.get("name"):
                raise ValidationError("客戶名稱為必填")
        if "status" in data and data["status"] not in STATUSES:
            raise ValidationError(f"狀態必須是：{'、'.join(STATUSES)}")
        if data.get("email") and "@" not in data["email"]:
            raise ValidationError("Email 格式不正確")

    def list_customers(self, q="", status="", sort="", order="asc"):
        sql = """
            SELECT c.*,
                   (SELECT COUNT(*) FROM interactions i WHERE i.customer_id = c.id)
                       AS interaction_count,
                   (SELECT MAX(contact_date) FROM interactions i WHERE i.customer_id = c.id)
                       AS last_contact
            FROM customers c WHERE 1=1
        """
        params = []
        if q:
            like = f"%{q.strip()}%"
            sql += """ AND (c.name LIKE ? OR c.company LIKE ? OR c.email LIKE ?
                          OR c.phone LIKE ? OR c.notes LIKE ?)"""
            params += [like] * 5
        if status:
            sql += " AND c.status = ?"
            params.append(status)
        if sort:
            if sort not in SORT_FIELDS:
                raise ValidationError(f"排序欄位必須是：{'、'.join(SORT_FIELDS)}")
            if order not in SORT_ORDERS:
                raise ValidationError("排序方向必須是 asc 或 desc")
            col = SORT_FIELDS[sort]
            # 空值（例如從未聯絡）無論升冪或降冪都排在最後
            sql += f" ORDER BY {col} IS NULL OR {col} = '', {col} {order.upper()}, c.id"
        else:
            sql += " ORDER BY c.updated_at DESC, c.id DESC"
        return [dict(r) for r in self.conn.execute(sql, params)]

    def get_customer(self, customer_id):
        row = self.conn.execute(
            "SELECT * FROM customers WHERE id = ?", (customer_id,)
        ).fetchone()
        return dict(row) if row else None

    def create_customer(self, data):
        data = _clean(data, CUSTOMER_FIELDS)
        data.setdefault("status", STATUSES[0])
        self._validate_customer(data)
        now = _now()
        data["created_at"] = data["updated_at"] = now
        cols = ", ".join(data)
        marks = ", ".join("?" for _ in data)
        cur = self.conn.execute(
            f"INSERT INTO customers ({cols}) VALUES ({marks})", list(data.values())
        )
        self.conn.commit()
        return self.get_customer(cur.lastrowid)

    def update_customer(self, customer_id, data):
        if not self.get_customer(customer_id):
            return None
        data = _clean(data, CUSTOMER_FIELDS)
        self._validate_customer(data, partial=True)
        data["updated_at"] = _now()
        sets = ", ".join(f"{k} = ?" for k in data)
        self.conn.execute(
            f"UPDATE customers SET {sets} WHERE id = ?", [*data.values(), customer_id]
        )
        self.conn.commit()
        return self.get_customer(customer_id)

    def delete_customer(self, customer_id):
        cur = self.conn.execute("DELETE FROM customers WHERE id = ?", (customer_id,))
        self.conn.commit()
        return cur.rowcount > 0

    def status_summary(self):
        counts = {s: 0 for s in STATUSES}
        for row in self.conn.execute(
            "SELECT status, COUNT(*) AS n FROM customers GROUP BY status"
        ):
            counts[row["status"]] = row["n"]
        return counts

    # ---------- 聯絡紀錄 ----------

    def list_interactions(self, customer_id):
        rows = self.conn.execute(
            """SELECT * FROM interactions WHERE customer_id = ?
               ORDER BY contact_date DESC, id DESC""",
            (customer_id,),
        )
        return [dict(r) for r in rows]

    def get_interaction(self, interaction_id):
        row = self.conn.execute(
            "SELECT * FROM interactions WHERE id = ?", (interaction_id,)
        ).fetchone()
        return dict(row) if row else None

    def _validate_interaction(self, data, partial=False):
        if not partial or "content" in data:
            if not data.get("content"):
                raise ValidationError("聯絡內容為必填")
        if not partial or "contact_date" in data:
            try:
                datetime.fromisoformat(data.get("contact_date", ""))
            except ValueError:
                raise ValidationError("聯絡日期格式不正確（YYYY-MM-DD）")
        if "method" in data and data["method"] not in CONTACT_METHODS:
            raise ValidationError(f"聯絡方式必須是：{'、'.join(CONTACT_METHODS)}")

    def create_interaction(self, customer_id, data):
        if not self.get_customer(customer_id):
            return None
        data = _clean(data, INTERACTION_FIELDS)
        data.setdefault("contact_date", datetime.now().date().isoformat())
        data.setdefault("method", "其他")
        self._validate_interaction(data)
        now = _now()
        cur = self.conn.execute(
            """INSERT INTO interactions (customer_id, contact_date, method, content, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (customer_id, data["contact_date"], data["method"], data["content"], now),
        )
        # 有新的聯絡紀錄時，一併更新客戶的最後更新時間
        self.conn.execute(
            "UPDATE customers SET updated_at = ? WHERE id = ?", (now, customer_id)
        )
        self.conn.commit()
        return self.get_interaction(cur.lastrowid)

    def update_interaction(self, interaction_id, data):
        if not self.get_interaction(interaction_id):
            return None
        data = _clean(data, INTERACTION_FIELDS)
        self._validate_interaction(data, partial=True)
        if data:
            sets = ", ".join(f"{k} = ?" for k in data)
            self.conn.execute(
                f"UPDATE interactions SET {sets} WHERE id = ?",
                [*data.values(), interaction_id],
            )
            self.conn.commit()
        return self.get_interaction(interaction_id)

    def delete_interaction(self, interaction_id):
        cur = self.conn.execute("DELETE FROM interactions WHERE id = ?", (interaction_id,))
        self.conn.commit()
        return cur.rowcount > 0

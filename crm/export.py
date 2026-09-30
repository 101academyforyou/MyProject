"""將客戶資料匯出為 CSV。"""

import csv
import io

# (欄位標題, 客戶資料的鍵)
CSV_COLUMNS = [
    ("編號", "id"),
    ("客戶名稱", "name"),
    ("公司", "company"),
    ("Email", "email"),
    ("電話", "phone"),
    ("地址", "address"),
    ("狀態", "status"),
    ("備註", "notes"),
    ("聯絡紀錄筆數", "interaction_count"),
    ("最後聯絡日期", "last_contact"),
    ("建立時間", "created_at"),
    ("更新時間", "updated_at"),
]

# 以這些字元開頭的儲存格，Excel 等試算表軟體會當成公式執行
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _cell(value):
    if value is None:
        return ""
    text = str(value)
    if text.startswith(_FORMULA_PREFIXES):
        # 前置單引號，避免 CSV 公式注入（例如 =HYPERLINK(...)）
        return "'" + text
    return text


def customers_to_csv(customers):
    """回傳 UTF-8（含 BOM，讓 Excel 正確顯示中文）編碼的 CSV 位元組。"""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\r\n")
    writer.writerow([title for title, _ in CSV_COLUMNS])
    for c in customers:
        writer.writerow([_cell(c.get(key)) for _, key in CSV_COLUMNS])
    return ("﻿" + buf.getvalue()).encode("utf-8")

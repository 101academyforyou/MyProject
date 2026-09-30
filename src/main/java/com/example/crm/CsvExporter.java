package com.example.crm;

import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;

/** 將客戶資料匯出為 CSV。 */
public final class CsvExporter {

    // {欄位標題, 客戶資料的鍵}
    private static final String[][] COLUMNS = {
        {"編號", "id"},
        {"客戶名稱", "name"},
        {"公司", "company"},
        {"Email", "email"},
        {"電話", "phone"},
        {"地址", "address"},
        {"狀態", "status"},
        {"備註", "notes"},
        {"聯絡紀錄筆數", "interaction_count"},
        {"最後聯絡日期", "last_contact"},
        {"建立時間", "created_at"},
        {"更新時間", "updated_at"},
    };

    private CsvExporter() {
    }

    /** 回傳 UTF-8（含 BOM，讓 Excel 正確顯示中文）編碼的 CSV 位元組。 */
    public static byte[] toCsv(List<Map<String, Object>> customers) {
        StringBuilder sb = new StringBuilder("﻿");
        for (int i = 0; i < COLUMNS.length; i++) {
            if (i > 0) {
                sb.append(',');
            }
            sb.append(quote(COLUMNS[i][0]));
        }
        sb.append("\r\n");
        for (Map<String, Object> c : customers) {
            for (int i = 0; i < COLUMNS.length; i++) {
                if (i > 0) {
                    sb.append(',');
                }
                sb.append(quote(cell(c.get(COLUMNS[i][1]))));
            }
            sb.append("\r\n");
        }
        return sb.toString().getBytes(StandardCharsets.UTF_8);
    }

    /** 以這些字元開頭的儲存格，Excel 等試算表軟體會當成公式執行，前置單引號避免 CSV 公式注入。 */
    static String cell(Object value) {
        if (value == null) {
            return "";
        }
        String text = value.toString();
        if (!text.isEmpty() && "=+-@\t\r".indexOf(text.charAt(0)) >= 0) {
            return "'" + text;
        }
        return text;
    }

    /** 含逗號、引號或換行的欄位以雙引號包住，內部引號重複一次（RFC 4180）。 */
    static String quote(String s) {
        if (s.contains(",") || s.contains("\"") || s.contains("\n") || s.contains("\r")) {
            return "\"" + s.replace("\"", "\"\"") + "\"";
        }
        return s;
    }
}

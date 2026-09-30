# MyProject — 客戶管理系統

[![Tests](https://github.com/101academyforyou/MyProject/actions/workflows/test.yml/badge.svg)](https://github.com/101academyforyou/MyProject/actions/workflows/test.yml)

用 Claude 開發。一個簡單的客戶管理（CRM）系統，只需要 Python 3.9 以上，**不需安裝任何套件**。

## 功能

- **客戶管理**：新增、修改、刪除客戶（名稱、公司、Email、電話、地址、備註）
- **搜尋**：以名稱、公司、Email、電話、備註關鍵字搜尋
- **CSV 匯出**：將目前搜尋／篩選結果匯出成 CSV（含 BOM，可直接用 Excel 開啟中文）
- **客戶狀態**：潛在客戶 / 洽談中 / 已成交 / 暫停 / 流失，可依狀態篩選，首頁顯示各狀態數量
- **聯絡紀錄**：記錄每次聯絡的日期、方式（電話、Email、會議、拜訪…）與內容，依時間排列
- 刪除客戶時，其聯絡紀錄會一併刪除

## 啟動

```bash
python3 app.py
```

打開瀏覽器前往 http://127.0.0.1:8000 。資料儲存在 `crm.db`（SQLite）。

可選參數：

```bash
python3 app.py --port 9000 --db 公司客戶.db --host 0.0.0.0
```

> 注意：此系統沒有登入機制，若使用 `--host 0.0.0.0` 開放給其他電腦連線，請只在可信任的內部網路使用。

## 測試

```bash
python3 -m unittest discover -s tests -t .
```

每次推送到 `main` 或開啟 Pull Request 時，GitHub Actions 會自動在 Python 3.9、3.11、3.13 上執行測試（設定檔：`.github/workflows/test.yml`）。

## 專案結構

```
app.py              啟動程式
crm/db.py           資料庫（SQLite）與資料驗證
crm/server.py       HTTP 伺服器與 REST API
crm/export.py       CSV 匯出
crm/static/         前端網頁（HTML / CSS / JavaScript）
tests/test_api.py   API 測試
```

## API

| 方法 | 路徑 | 說明 |
|---|---|---|
| GET | `/api/meta` | 狀態清單、聯絡方式清單、各狀態客戶數 |
| GET | `/api/customers?q=關鍵字&status=狀態` | 列出 / 搜尋客戶 |
| GET | `/api/customers/export.csv?q=關鍵字&status=狀態` | 以 CSV 匯出符合條件的客戶 |
| POST | `/api/customers` | 新增客戶 |
| GET | `/api/customers/{id}` | 取得客戶 |
| PUT | `/api/customers/{id}` | 修改客戶（可只傳要修改的欄位） |
| DELETE | `/api/customers/{id}` | 刪除客戶 |
| GET | `/api/customers/{id}/interactions` | 列出聯絡紀錄 |
| POST | `/api/customers/{id}/interactions` | 新增聯絡紀錄 |
| PUT | `/api/interactions/{id}` | 修改聯絡紀錄 |
| DELETE | `/api/interactions/{id}` | 刪除聯絡紀錄 |

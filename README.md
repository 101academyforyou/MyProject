# MyProject — 客戶管理系統

[![Tests](https://github.com/101academyforyou/MyProject/actions/workflows/test.yml/badge.svg)](https://github.com/101academyforyou/MyProject/actions/workflows/test.yml)

用 Claude 開發。一個簡單的客戶管理（CRM）系統，使用 **Java 17 + Spring Boot + SQLite**，可直接在 IntelliJ IDEA 執行。

## 功能

- **客戶管理**：新增、修改、刪除客戶（名稱、公司、Email、電話、地址、備註）
- **搜尋**：以名稱、公司、Email、電話、備註關鍵字搜尋
- **CSV 匯出**：將目前搜尋／篩選結果匯出成 CSV（含 BOM，可直接用 Excel 開啟中文）
- **客戶狀態**：潛在客戶 / 洽談中 / 已成交 / 暫停 / 流失，可依狀態篩選，首頁顯示各狀態數量
- **聯絡紀錄**：記錄每次聯絡的日期、方式（電話、Email、會議、拜訪…）與內容，依時間排列
- 刪除客戶時，其聯絡紀錄會一併刪除

## 在 IntelliJ IDEA 執行

需要 **JDK 17 以上**（IntelliJ 可在 *File → Project Structure → SDK* 直接下載）。Community 版即可。

1. *File → Open*，選擇專案資料夾（含 `pom.xml` 的那層），IntelliJ 會自動以 Maven 專案匯入並下載相依套件。
2. 右上角執行設定選 **CrmApplication**，按 ▶ 執行
   （或開啟 `src/main/java/com/example/crm/CrmApplication.java`，點 `main` 方法旁的 ▶）。
3. 瀏覽器開啟 http://localhost:8000 。

資料儲存在專案根目錄的 `crm.db`（SQLite），與先前 Python 版的資料庫格式相同，可直接沿用。

## 命令列執行

```bash
mvn spring-boot:run
```

或先打包成單一 jar：

```bash
mvn package
java -jar target/crm-1.0.0.jar
```

可用參數覆寫設定，例如：

```bash
java -jar target/crm-1.0.0.jar --server.port=9000 --spring.datasource.url=jdbc:sqlite:公司客戶.db
```

> 注意：此系統沒有登入機制，預設只接受本機連線。若要讓其他電腦連線，請加上 `--server.address=0.0.0.0`，並只在可信任的內部網路使用。

## 測試

在 IntelliJ 對 `src/test/java` 按右鍵 → *Run 'All Tests'*，或：

```bash
mvn test
```

每次推送到 `main` 或開啟 Pull Request 時，GitHub Actions 會自動在 Java 17、21 上執行測試（設定檔：`.github/workflows/test.yml`）。

## 專案結構

```
pom.xml                                   Maven 設定與相依套件
src/main/java/com/example/crm/
  CrmApplication.java                     程式進入點（main）
  CrmController.java                      REST API
  CrmService.java                         資料存取與驗證
  CsvExporter.java                        CSV 匯出
  ApiExceptionHandler.java                錯誤回應格式
src/main/resources/
  application.properties                  連接埠、資料庫等設定
  schema.sql                              資料表定義
  static/                                 前端網頁（HTML / CSS / JavaScript）
src/test/java/com/example/crm/
  CrmApiTest.java                         API 測試
.run/CrmApplication.run.xml               IntelliJ 共用執行設定
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

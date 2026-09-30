package com.example.crm;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.IOException;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.web.client.RestClient;

/** 啟動真正的伺服器，以 HTTP 呼叫 API 測試（與原 Python 版 tests/test_api.py 對應）。 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class CrmApiTest {

    @DynamicPropertySource
    static void database(DynamicPropertyRegistry registry) throws IOException {
        Path db = Files.createTempFile("crm-test", ".db");
        db.toFile().deleteOnExit();
        registry.add("spring.datasource.url", () -> "jdbc:sqlite:" + db);
    }

    @LocalServerPort
    int port;

    @Autowired
    JdbcTemplate jdbc;

    RestClient http;

    @BeforeEach
    void setUp() {
        jdbc.update("DELETE FROM interactions");
        jdbc.update("DELETE FROM customers");
        http = RestClient.create("http://localhost:" + port);
    }

    // ---------- 工具 ----------

    /** 以 URI 物件傳入，避免 RestClient 把已編碼的查詢字串再編碼一次。 */
    private URI uri(String path) {
        return URI.create("http://localhost:" + port + path);
    }

    record Response<T>(int status, T body) {
    }

    private <T> Response<T> call(HttpMethod method, String path, Object body, ParameterizedTypeReference<T> type) {
        var req = http.method(method).uri(uri(path));
        if (body != null) {
            req = req.contentType(MediaType.APPLICATION_JSON).body(body);
        }
        return req.exchange((rq, rs) -> new Response<>(rs.getStatusCode().value(), rs.bodyTo(type)));
    }

    private Response<Map<String, Object>> obj(HttpMethod method, String path, Object body) {
        return call(method, path, body, new ParameterizedTypeReference<>() {
        });
    }

    private Response<Map<String, Object>> obj(HttpMethod method, String path) {
        return obj(method, path, null);
    }

    private List<Map<String, Object>> list(String path) {
        Response<List<Map<String, Object>>> r = call(HttpMethod.GET, path, null,
                new ParameterizedTypeReference<>() {
                });
        assertEquals(200, r.status());
        return r.body();
    }

    private Map<String, Object> create(Map<String, Object> fields) {
        Map<String, Object> data = new HashMap<>(fields);
        data.putIfAbsent("name", "王小明");
        Response<Map<String, Object>> r = obj(HttpMethod.POST, "/api/customers", data);
        assertEquals(201, r.status(), String.valueOf(r.body()));
        return r.body();
    }

    private static long id(Map<String, Object> row) {
        return ((Number) row.get("id")).longValue();
    }

    private static Set<Object> names(List<Map<String, Object>> rows) {
        return rows.stream().map(r -> r.get("name")).collect(Collectors.toSet());
    }

    // ---------- 客戶 ----------

    @Test
    void customerCrud() {
        Map<String, Object> c = create(Map.of("company", "大明科技", "email", "ming@example.com",
                "phone", "0912345678"));
        assertEquals("潛在客戶", c.get("status"));

        var got = obj(HttpMethod.GET, "/api/customers/" + id(c));
        assertEquals(200, got.status());
        assertEquals("大明科技", got.body().get("company"));

        var upd = obj(HttpMethod.PUT, "/api/customers/" + id(c), Map.of("status", "洽談中"));
        assertEquals(200, upd.status());
        assertEquals("洽談中", upd.body().get("status"));
        assertEquals("王小明", upd.body().get("name"));

        assertEquals(200, obj(HttpMethod.DELETE, "/api/customers/" + id(c)).status());
        assertEquals(404, obj(HttpMethod.GET, "/api/customers/" + id(c)).status());
        assertEquals(404, obj(HttpMethod.DELETE, "/api/customers/" + id(c)).status());
    }

    @Test
    void validation() {
        var r = obj(HttpMethod.POST, "/api/customers", Map.of("name", "  "));
        assertEquals(400, r.status());
        assertTrue(r.body().get("error").toString().contains("必填"));
        assertEquals(400, obj(HttpMethod.POST, "/api/customers", Map.of("name", "A", "status", "不存在")).status());
        assertEquals(400, obj(HttpMethod.POST, "/api/customers", Map.of("name", "A", "email", "bad")).status());
        assertEquals(404, obj(HttpMethod.PUT, "/api/customers/999", Map.of("name", "X")).status());

        // 請求內容不是 JSON 物件
        var bad = obj(HttpMethod.POST, "/api/customers", List.of(1, 2));
        assertEquals(400, bad.status());
        assertEquals("JSON 格式錯誤", bad.body().get("error"));
    }

    @Test
    void searchAndFilter() {
        create(Map.of("name", "王小明", "company", "大明科技"));
        create(Map.of("name", "李美華", "company", "美華貿易", "status", "已成交"));
        create(Map.of("name", "陳大同", "notes", "介紹人：大明", "status", "已成交"));

        assertEquals(Set.of("王小明", "陳大同"), names(list("/api/customers?q=" + enc("大明"))));
        assertEquals(Set.of("李美華", "陳大同"), names(list("/api/customers?status=" + enc("已成交"))));

        var meta = obj(HttpMethod.GET, "/api/meta").body();
        @SuppressWarnings("unchecked")
        Map<String, Object> summary = (Map<String, Object>) meta.get("summary");
        assertEquals(2, ((Number) summary.get("已成交")).intValue());
        assertEquals(1, ((Number) summary.get("潛在客戶")).intValue());
        assertEquals(CrmService.STATUSES, meta.get("statuses"));
    }

    // ---------- 聯絡紀錄 ----------

    @Test
    void interactions() {
        Map<String, Object> c = create(Map.of());
        String path = "/api/customers/" + id(c) + "/interactions";
        var i1 = obj(HttpMethod.POST, path, Map.of("contact_date", "2026-09-01", "method", "電話",
                "content", "初次聯繫"));
        assertEquals(201, i1.status());
        obj(HttpMethod.POST, path, Map.of("contact_date", "2026-09-15", "method", "會議", "content", "報價"));

        assertEquals(List.of("報價", "初次聯繫"),
                list(path).stream().map(i -> i.get("content")).toList());

        var rows = list("/api/customers");
        assertEquals(2, ((Number) rows.get(0).get("interaction_count")).intValue());
        assertEquals("2026-09-15", rows.get(0).get("last_contact"));

        long i1Id = id(i1.body());
        var upd = obj(HttpMethod.PUT, "/api/interactions/" + i1Id, Map.of("content", "初次電話聯繫"));
        assertEquals(200, upd.status());
        assertEquals("初次電話聯繫", upd.body().get("content"));

        assertEquals(400, obj(HttpMethod.POST, path, Map.of("content", "")).status());
        assertEquals(400, obj(HttpMethod.POST, path, Map.of("content", "x", "contact_date", "昨天")).status());
        assertEquals(400, obj(HttpMethod.POST, path, Map.of("content", "x", "method", "飛鴿傳書")).status());
        assertEquals(404, obj(HttpMethod.POST, "/api/customers/999/interactions", Map.of("content", "x")).status());

        obj(HttpMethod.DELETE, "/api/interactions/" + i1Id);
        assertEquals(1, list(path).size());

        // 刪除客戶時，聯絡紀錄一併刪除
        obj(HttpMethod.DELETE, "/api/customers/" + id(c));
        assertEquals(0, jdbc.queryForObject("SELECT COUNT(*) FROM interactions", Integer.class));
    }

    // ---------- CSV 匯出 ----------

    private List<List<String>> export(String query) {
        Response<byte[]> r = http.get().uri(uri("/api/customers/export.csv?" + query))
                .exchange((rq, rs) -> {
                    HttpHeaders h = rs.getHeaders();
                    assertTrue(h.getContentType().toString().startsWith("text/csv"));
                    assertTrue(h.getFirst(HttpHeaders.CONTENT_DISPOSITION).contains("attachment"));
                    return new Response<>(rs.getStatusCode().value(), rs.bodyTo(byte[].class));
                });
        assertEquals(200, r.status());
        byte[] raw = r.body();
        assertTrue(raw.length >= 3 && (raw[0] & 0xFF) == 0xEF && (raw[1] & 0xFF) == 0xBB
                && (raw[2] & 0xFF) == 0xBF, "應包含 UTF-8 BOM 供 Excel 辨識");
        return parseCsv(new String(raw, 3, raw.length - 3, StandardCharsets.UTF_8));
    }

    /** 簡易 RFC 4180 解析器，用來驗證匯出內容。 */
    private static List<List<String>> parseCsv(String text) {
        List<List<String>> rows = new ArrayList<>();
        List<String> row = new ArrayList<>();
        StringBuilder cell = new StringBuilder();
        boolean quoted = false;
        for (int i = 0; i < text.length(); i++) {
            char ch = text.charAt(i);
            if (quoted) {
                if (ch == '"' && i + 1 < text.length() && text.charAt(i + 1) == '"') {
                    cell.append('"');
                    i++;
                } else if (ch == '"') {
                    quoted = false;
                } else {
                    cell.append(ch);
                }
            } else if (ch == '"') {
                quoted = true;
            } else if (ch == ',') {
                row.add(cell.toString());
                cell.setLength(0);
            } else if (ch == '\r' && i + 1 < text.length() && text.charAt(i + 1) == '\n') {
                row.add(cell.toString());
                cell.setLength(0);
                rows.add(row);
                row = new ArrayList<>();
                i++;
            } else {
                cell.append(ch);
            }
        }
        return rows;
    }

    private static Map<String, String> asRecord(List<String> header, List<String> row) {
        Map<String, String> m = new HashMap<>();
        for (int i = 0; i < header.size(); i++) {
            m.put(header.get(i), row.get(i));
        }
        return m;
    }

    @Test
    void exportCsv() {
        Map<String, Object> a = create(Map.of("name", "王小明", "company", "大明科技",
                "email", "ming@example.com", "notes", "第一行\n第二行, 含逗號與\"引號\""));
        create(Map.of("name", "李美華", "company", "美華貿易", "status", "已成交"));
        obj(HttpMethod.POST, "/api/customers/" + id(a) + "/interactions",
                Map.of("contact_date", "2026-09-15", "content", "x"));

        var rows = export("");
        var header = rows.get(0);
        assertEquals(List.of("編號", "客戶名稱", "公司"), header.subList(0, 3));
        assertEquals(3, rows.size());
        var ming = asRecord(header, rows.stream().filter(r -> r.get(1).equals("王小明")).findFirst().orElseThrow());
        assertEquals("ming@example.com", ming.get("Email"));
        assertEquals("第一行\n第二行, 含逗號與\"引號\"", ming.get("備註"));
        assertEquals("1", ming.get("聯絡紀錄筆數"));
        assertEquals("2026-09-15", ming.get("最後聯絡日期"));
    }

    @Test
    void exportCsvUsesSearchAndFilter() {
        create(Map.of("name", "王小明", "company", "大明科技"));
        create(Map.of("name", "李美華", "company", "美華貿易", "status", "已成交"));
        create(Map.of("name", "陳大同", "notes", "大明介紹", "status", "已成交"));

        assertEquals(Set.of("王小明", "陳大同"), secondColumn(export("q=" + enc("大明"))));
        assertEquals(Set.of("李美華", "陳大同"), secondColumn(export("status=" + enc("已成交"))));
        assertEquals(Set.of("陳大同"), secondColumn(export("q=" + enc("大明") + "&status=" + enc("已成交"))));
        // 沒有符合的資料時仍輸出標題列
        assertEquals(1, export("q=nobody").size());
    }

    @Test
    void exportCsvEscapesFormulas() {
        create(Map.of("name", "=HYPERLINK(\"http://evil\")", "phone", "+886 912 345 678", "notes", "@SUM(A1)"));
        var rows = export("");
        var row = asRecord(rows.get(0), rows.get(1));
        assertEquals("'=HYPERLINK(\"http://evil\")", row.get("客戶名稱"));
        assertEquals("'+886 912 345 678", row.get("電話"));
        assertEquals("'@SUM(A1)", row.get("備註"));
    }

    // ---------- 網頁 ----------

    @Test
    void staticFiles() {
        String html = http.get().uri("/").retrieve().body(String.class);
        assertTrue(html.contains("客戶管理系統"));
        assertEquals(404, obj(HttpMethod.GET, "/api/nope").status());
    }

    private static Set<String> secondColumn(List<List<String>> rows) {
        return rows.stream().skip(1).map(r -> r.get(1)).collect(Collectors.toSet());
    }

    private static String enc(String s) {
        return java.net.URLEncoder.encode(s, StandardCharsets.UTF_8);
    }
}

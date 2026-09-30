package com.example.crm;

import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 客戶與聯絡紀錄的資料存取與驗證。 */
@Service
public class CrmService {

    public static final List<String> STATUSES = List.of("潛在客戶", "洽談中", "已成交", "暫停", "流失");
    public static final List<String> CONTACT_METHODS =
            List.of("電話", "Email", "會議", "拜訪", "通訊軟體", "其他");

    // 可由 API 寫入的欄位（白名單，SQL 欄位名稱只會來自這裡）
    private static final List<String> CUSTOMER_FIELDS =
            List.of("name", "company", "email", "phone", "address", "status", "notes");
    private static final List<String> INTERACTION_FIELDS = List.of("contact_date", "method", "content");

    private static final DateTimeFormatter TIMESTAMP = DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss");

    private final JdbcTemplate jdbc;

    public CrmService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    private static String now() {
        return LocalDateTime.now().format(TIMESTAMP);
    }

    /** 只保留允許的欄位，並將值轉為去除前後空白的字串。 */
    private static Map<String, Object> clean(Map<String, Object> data, List<String> fields) {
        Map<String, Object> out = new LinkedHashMap<>();
        for (String f : fields) {
            Object v = data.get(f);
            if (v != null) {
                out.put(f, v.toString().strip());
            }
        }
        return out;
    }

    private static boolean isBlank(Object v) {
        return v == null || v.toString().isEmpty();
    }

    // ---------- 客戶 ----------

    private void validateCustomer(Map<String, Object> data, boolean partial) {
        if ((!partial || data.containsKey("name")) && isBlank(data.get("name"))) {
            throw new ValidationException("客戶名稱為必填");
        }
        if (data.containsKey("status") && !STATUSES.contains(data.get("status"))) {
            throw new ValidationException("狀態必須是：" + String.join("、", STATUSES));
        }
        Object email = data.get("email");
        if (!isBlank(email) && !email.toString().contains("@")) {
            throw new ValidationException("Email 格式不正確");
        }
    }

    public List<Map<String, Object>> listCustomers(String q, String status) {
        StringBuilder sql = new StringBuilder("""
                SELECT c.*,
                       (SELECT COUNT(*) FROM interactions i WHERE i.customer_id = c.id)
                           AS interaction_count,
                       (SELECT MAX(contact_date) FROM interactions i WHERE i.customer_id = c.id)
                           AS last_contact
                FROM customers c WHERE 1=1
                """);
        List<Object> params = new ArrayList<>();
        if (q != null && !q.isBlank()) {
            String like = "%" + q.strip() + "%";
            sql.append(" AND (c.name LIKE ? OR c.company LIKE ? OR c.email LIKE ?"
                    + " OR c.phone LIKE ? OR c.notes LIKE ?)");
            for (int i = 0; i < 5; i++) {
                params.add(like);
            }
        }
        if (status != null && !status.isEmpty()) {
            sql.append(" AND c.status = ?");
            params.add(status);
        }
        sql.append(" ORDER BY c.updated_at DESC, c.id DESC");
        return jdbc.queryForList(sql.toString(), params.toArray());
    }

    public Map<String, Object> getCustomer(long id) {
        List<Map<String, Object>> rows = jdbc.queryForList("SELECT * FROM customers WHERE id = ?", id);
        if (rows.isEmpty()) {
            throw new NotFoundException();
        }
        return rows.get(0);
    }

    @Transactional
    public Map<String, Object> createCustomer(Map<String, Object> input) {
        Map<String, Object> data = clean(input, CUSTOMER_FIELDS);
        data.putIfAbsent("status", STATUSES.get(0));
        validateCustomer(data, false);
        String now = now();
        data.put("created_at", now);
        data.put("updated_at", now);
        return getCustomer(insert("customers", data));
    }

    @Transactional
    public Map<String, Object> updateCustomer(long id, Map<String, Object> input) {
        getCustomer(id);
        Map<String, Object> data = clean(input, CUSTOMER_FIELDS);
        validateCustomer(data, true);
        data.put("updated_at", now());
        update("customers", id, data);
        return getCustomer(id);
    }

    public void deleteCustomer(long id) {
        if (jdbc.update("DELETE FROM customers WHERE id = ?", id) == 0) {
            throw new NotFoundException();
        }
    }

    public Map<String, Integer> statusSummary() {
        Map<String, Integer> counts = new LinkedHashMap<>();
        STATUSES.forEach(s -> counts.put(s, 0));
        jdbc.query("SELECT status, COUNT(*) AS n FROM customers GROUP BY status",
                rs -> {
                    counts.put(rs.getString("status"), rs.getInt("n"));
                });
        return counts;
    }

    // ---------- 聯絡紀錄 ----------

    private void validateInteraction(Map<String, Object> data, boolean partial) {
        if ((!partial || data.containsKey("content")) && isBlank(data.get("content"))) {
            throw new ValidationException("聯絡內容為必填");
        }
        if (!partial || data.containsKey("contact_date")) {
            if (!isIsoDate(data.get("contact_date"))) {
                throw new ValidationException("聯絡日期格式不正確（YYYY-MM-DD）");
            }
        }
        if (data.containsKey("method") && !CONTACT_METHODS.contains(data.get("method"))) {
            throw new ValidationException("聯絡方式必須是：" + String.join("、", CONTACT_METHODS));
        }
    }

    /** 接受 YYYY-MM-DD 或 YYYY-MM-DDTHH:MM[:SS]。 */
    private static boolean isIsoDate(Object value) {
        if (value == null) {
            return false;
        }
        String s = value.toString();
        try {
            LocalDate.parse(s);
            return true;
        } catch (DateTimeParseException e) {
            try {
                LocalDateTime.parse(s);
                return true;
            } catch (DateTimeParseException e2) {
                return false;
            }
        }
    }

    public List<Map<String, Object>> listInteractions(long customerId) {
        getCustomer(customerId);
        return jdbc.queryForList(
                "SELECT * FROM interactions WHERE customer_id = ? ORDER BY contact_date DESC, id DESC",
                customerId);
    }

    public Map<String, Object> getInteraction(long id) {
        List<Map<String, Object>> rows = jdbc.queryForList("SELECT * FROM interactions WHERE id = ?", id);
        if (rows.isEmpty()) {
            throw new NotFoundException();
        }
        return rows.get(0);
    }

    @Transactional
    public Map<String, Object> createInteraction(long customerId, Map<String, Object> input) {
        getCustomer(customerId);
        Map<String, Object> data = clean(input, INTERACTION_FIELDS);
        data.putIfAbsent("contact_date", LocalDate.now().toString());
        data.putIfAbsent("method", "其他");
        validateInteraction(data, false);
        String now = now();
        data.put("customer_id", customerId);
        data.put("created_at", now);
        long id = insert("interactions", data);
        // 有新的聯絡紀錄時，一併更新客戶的最後更新時間
        jdbc.update("UPDATE customers SET updated_at = ? WHERE id = ?", now, customerId);
        return getInteraction(id);
    }

    @Transactional
    public Map<String, Object> updateInteraction(long id, Map<String, Object> input) {
        getInteraction(id);
        Map<String, Object> data = clean(input, INTERACTION_FIELDS);
        validateInteraction(data, true);
        if (!data.isEmpty()) {
            update("interactions", id, data);
        }
        return getInteraction(id);
    }

    public void deleteInteraction(long id) {
        if (jdbc.update("DELETE FROM interactions WHERE id = ?", id) == 0) {
            throw new NotFoundException();
        }
    }

    // ---------- 共用 ----------

    private long insert(String table, Map<String, Object> data) {
        String cols = String.join(", ", data.keySet());
        String marks = data.keySet().stream().map(k -> "?").collect(Collectors.joining(", "));
        GeneratedKeyHolder keys = new GeneratedKeyHolder();
        jdbc.update(con -> {
            var ps = con.prepareStatement(
                    "INSERT INTO " + table + " (" + cols + ") VALUES (" + marks + ")",
                    java.sql.Statement.RETURN_GENERATED_KEYS);
            int i = 1;
            for (Object v : data.values()) {
                ps.setObject(i++, v);
            }
            return ps;
        }, keys);
        return keys.getKey().longValue();
    }

    private void update(String table, long id, Map<String, Object> data) {
        String sets = data.keySet().stream().map(k -> k + " = ?").collect(Collectors.joining(", "));
        List<Object> params = new ArrayList<>(data.values());
        params.add(id);
        jdbc.update("UPDATE " + table + " SET " + sets + " WHERE id = ?", params.toArray());
    }
}

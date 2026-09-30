package com.example.crm;

import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.List;
import java.util.Map;

import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

/** REST API，路徑與回應格式與前端 app.js 對應。 */
@RestController
@RequestMapping("/api")
public class CrmController {

    private static final Map<String, Boolean> OK = Map.of("ok", true);

    private final CrmService crm;

    public CrmController(CrmService crm) {
        this.crm = crm;
    }

    @GetMapping("/meta")
    public Map<String, Object> meta() {
        return Map.of(
                "statuses", CrmService.STATUSES,
                "contact_methods", CrmService.CONTACT_METHODS,
                "summary", crm.statusSummary());
    }

    // ---------- 客戶 ----------

    @GetMapping("/customers")
    public List<Map<String, Object>> listCustomers(
            @RequestParam(defaultValue = "") String q,
            @RequestParam(defaultValue = "") String status) {
        return crm.listCustomers(q, status);
    }

    @GetMapping("/customers/export.csv")
    public ResponseEntity<byte[]> exportCustomers(
            @RequestParam(defaultValue = "") String q,
            @RequestParam(defaultValue = "") String status) {
        String filename = "customers-"
                + LocalDateTime.now().format(DateTimeFormatter.ofPattern("yyyyMMdd-HHmmss")) + ".csv";
        return ResponseEntity.ok()
                .contentType(new MediaType("text", "csv", java.nio.charset.StandardCharsets.UTF_8))
                .header(HttpHeaders.CONTENT_DISPOSITION, "attachment; filename=\"" + filename + "\"")
                .body(CsvExporter.toCsv(crm.listCustomers(q, status)));
    }

    @PostMapping("/customers")
    @ResponseStatus(HttpStatus.CREATED)
    public Map<String, Object> createCustomer(@RequestBody Map<String, Object> body) {
        return crm.createCustomer(body);
    }

    @GetMapping("/customers/{id:\\d+}")
    public Map<String, Object> getCustomer(@PathVariable long id) {
        return crm.getCustomer(id);
    }

    @PutMapping("/customers/{id:\\d+}")
    public Map<String, Object> updateCustomer(@PathVariable long id, @RequestBody Map<String, Object> body) {
        return crm.updateCustomer(id, body);
    }

    @DeleteMapping("/customers/{id:\\d+}")
    public Map<String, Boolean> deleteCustomer(@PathVariable long id) {
        crm.deleteCustomer(id);
        return OK;
    }

    // ---------- 聯絡紀錄 ----------

    @GetMapping("/customers/{id:\\d+}/interactions")
    public List<Map<String, Object>> listInteractions(@PathVariable long id) {
        return crm.listInteractions(id);
    }

    @PostMapping("/customers/{id:\\d+}/interactions")
    @ResponseStatus(HttpStatus.CREATED)
    public Map<String, Object> createInteraction(@PathVariable long id, @RequestBody Map<String, Object> body) {
        return crm.createInteraction(id, body);
    }

    @PutMapping("/interactions/{id:\\d+}")
    public Map<String, Object> updateInteraction(@PathVariable long id, @RequestBody Map<String, Object> body) {
        return crm.updateInteraction(id, body);
    }

    @DeleteMapping("/interactions/{id:\\d+}")
    public Map<String, Boolean> deleteInteraction(@PathVariable long id) {
        crm.deleteInteraction(id);
        return OK;
    }
}

package com.example.crm;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/**
 * 客戶管理系統進入點。
 *
 * <p>在 IntelliJ 中直接執行此類別的 main 方法，然後以瀏覽器開啟 http://localhost:8000 。
 */
@SpringBootApplication
public class CrmApplication {

    public static void main(String[] args) {
        SpringApplication.run(CrmApplication.class, args);
    }
}

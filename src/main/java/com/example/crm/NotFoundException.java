package com.example.crm;

/** 找不到指定的資料，回應 HTTP 404。 */
public class NotFoundException extends RuntimeException {

    public NotFoundException() {
        super("找不到資料");
    }
}

package com.example.crm;

/** 輸入資料不正確，回應 HTTP 400。 */
public class ValidationException extends RuntimeException {

    public ValidationException(String message) {
        super(message);
    }
}

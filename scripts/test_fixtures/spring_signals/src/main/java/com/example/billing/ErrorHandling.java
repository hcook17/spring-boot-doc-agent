package com.example.billing;

import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
class GlobalErrors {
    @ExceptionHandler(IllegalStateException.class)
    public String handle(IllegalStateException e) { return "x"; }
}

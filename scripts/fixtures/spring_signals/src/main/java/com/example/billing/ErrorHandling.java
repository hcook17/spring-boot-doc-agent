package com.example.billing;

import org.springframework.web.bind.annotation.ControllerAdvice;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@ControllerAdvice
class MvcErrors {
    @ExceptionHandler(IllegalArgumentException.class)
    public String handleMvc(IllegalArgumentException e) { return "mvc"; }
}

@RestControllerAdvice
class GlobalErrors {
    @ExceptionHandler(IllegalStateException.class)
    public String handle(IllegalStateException e) { return "x"; }
}

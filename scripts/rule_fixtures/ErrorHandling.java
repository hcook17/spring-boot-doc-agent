package com.example.fixtures;

@RestControllerAdvice
public class Errors {
    @ExceptionHandler(IllegalStateException.class)
    public String handle(IllegalStateException e) { return "x"; }
}

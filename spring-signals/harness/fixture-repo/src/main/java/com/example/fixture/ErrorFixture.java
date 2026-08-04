package com.example.fixture;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.server.ResponseStatusException;

@RestControllerAdvice
public class ErrorFixture {

  @ExceptionHandler({IllegalArgumentException.class, IllegalStateException.class})
  @ResponseStatus(HttpStatus.BAD_REQUEST)
  public String onBadRequest(RuntimeException e) {
    return e.getMessage();
  }

  public void boom() {
    throw new ResponseStatusException(HttpStatus.NOT_FOUND, "missing");
  }

  public void boomAgain() {
    throw new ResponseStatusException(HttpStatus.CONFLICT);
  }
}

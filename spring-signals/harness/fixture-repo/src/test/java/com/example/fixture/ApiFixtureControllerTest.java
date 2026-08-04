package com.example.fixture;

import org.junit.jupiter.api.Test;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

/** Lives in src/test/java: every row from here must carry source_set=test. */
class ApiFixtureControllerTest {

  @Test
  void getBookReturnsId() {
    ApiFixtureController c = new ApiFixtureController();
    assert "7".equals(c.getBook("7"));
  }
}

@RestController
class TestOnlyController {
  @GetMapping("/test-only")
  String testOnly() {
    return "x";
  }
}

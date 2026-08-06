package com.example.fixture;

import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/** @RestController is meta-annotated @Controller; exercises SpringMetaEdges. */
@RestController
@RequestMapping("/api/v1/books")
public class ApiFixtureController {

  @GetMapping("/{id}")
  public String getBook(@PathVariable("id") String id) {
    return id;
  }

  /** `q` has no declared name: this is the -parameters finding. */
  @GetMapping
  public String search(@RequestParam String q, @RequestParam(value = "page") int page) {
    return q + page;
  }

  /** @RequestBody can never carry a name; empty detail here is NOT a finding. */
  @PostMapping("/bulk")
  public String bulk(@RequestBody String payload) {
    return payload;
  }

  @DeleteMapping({"/{id}", "/legacy/{id}"})
  public void delete(@PathVariable("id") String id) {}
}

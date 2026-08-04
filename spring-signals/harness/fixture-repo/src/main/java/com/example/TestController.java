package com.example;

import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RequestBody;

@RestController
@RequestMapping("/api/v1/books")
public class TestController {
    @GetMapping("/{id}")
    public String getBook(
        @PathVariable("id") String id,
        @RequestParam("q") String q
    ) {
        return id;
    }

    @PostMapping
    public String createBook(@RequestBody String body) {
        return body;
    }

    @PutMapping("/{id}")
    public String updateBook(@PathVariable String id) {
        return id;
    }

    @DeleteMapping("/{id}")
    public String deleteBook(@PathVariable(name = "id") String id) {
        return id;
    }

    @PatchMapping("/{id}")
    public String patchBook(@PathVariable(value = "id") String id) {
        return id;
    }
}

package com.example;

import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestParam;

@RestController
@RequestMapping("/api/v1/books")
public class TestController {
    @GetMapping("/{id}")
    public String getBook(@PathVariable("id") String id, @RequestParam("q") String q) {
        return id;
    }
}

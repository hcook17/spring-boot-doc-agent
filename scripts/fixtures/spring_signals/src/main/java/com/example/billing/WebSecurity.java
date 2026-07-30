package com.example.billing;

import org.springframework.context.annotation.Bean;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

class WebSecurity {
    @Bean
    SecurityFilterChain chain(HttpSecurity http) { return null; }
}

package com.example;

import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.web.SecurityFilterChain;

@EnableWebSecurity
public class SecurityConfig {
    public SecurityFilterChain filterChain() {
        return null;
    }

    @org.springframework.security.access.prepost.PreAuthorize("hasRole('USER')")
    public String secured() {
        return "ok";
    }
}

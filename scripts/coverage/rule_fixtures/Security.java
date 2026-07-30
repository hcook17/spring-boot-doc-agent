package com.example.fixtures;

import org.springframework.security.config.annotation.web.builders.HttpSecurity;

@EnableWebSecurity
public class SecurityConfig {
    public SecurityFilterChain chain(HttpSecurity http) { return null; }
}

class Guarded {
    @PreAuthorize("hasRole('ADMIN')")
    public void admin() { }

    @Secured
    public void legacy() { }
}

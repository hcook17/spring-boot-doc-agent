package com.example.billing;

import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.web.client.RestTemplate;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.boot.autoconfigure.domain.EntityScan;
import org.testcontainers.containers.PostgreSQLContainer;

// Regression guard: @EntityScan must NOT be picked up by the
// persistence__entity rule just because it starts with "@Entity" — this is
// a real false positive the old regex scanner had ("@Entity" in text is a
// substring check, so "@EntityScan(...)" matched it). Found by running the
// old scanner against a real production codebase's Application.java (a
// @SpringBootApplication main class carrying @EntityScan to configure
// entity-scan base packages) — it got misfiled into entity_table_map as a
// fake "Application" entity with an inferred table name.
@EntityScan({"com.example.billing"})
@EnableWebSecurity
public class SecurityConfig {
    // Field type AND constructor-call type on one line — exercises the
    // dedup-by-(file, line, ruleId) collapse in spring_signal_scan.py, since
    // ast-grep correctly reports these as two distinct type_identifier
    // matches (RestTemplate declared, RestTemplate constructed).
    private final RestTemplate restTemplate = new RestTemplate();
    private final MeterRegistry meterRegistry;
}

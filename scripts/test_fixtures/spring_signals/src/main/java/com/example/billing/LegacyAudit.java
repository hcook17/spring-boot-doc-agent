package com.example.billing;

import jakarta.persistence.Entity;

// No @Table — exercises the inferred-default-naming fallback
// (Spring Data's snake_case-of-class-name convention).
@Entity
public class LegacyAudit {
    private Long id;
}

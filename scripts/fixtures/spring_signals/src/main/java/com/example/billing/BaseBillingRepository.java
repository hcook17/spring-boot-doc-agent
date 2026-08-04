package com.example.billing;

import org.springframework.data.jpa.repository.JpaRepository;

/** Intermediate Spring Data base — transitive repo chain (P0.3). */
public interface BaseBillingRepository extends JpaRepository<Invoice, Long> {
}

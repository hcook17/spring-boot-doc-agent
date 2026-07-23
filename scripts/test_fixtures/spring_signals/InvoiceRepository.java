package com.example.billing;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;

public interface InvoiceRepository extends JpaRepository<Invoice, Long> {

    // Positional argument, no nativeQuery flag -> jpql.
    @Query("SELECT i FROM Invoice i WHERE i.status = :status")
    Invoice findByStatus(String status);

    // Named arguments with nativeQuery=true AFTER the query string -> native.
    // Regression guard: the old this-line-or-next-line heuristic and a
    // fixed-argument-order pattern both handled this correctly only by
    // accident; this scanner reads the whole @Query argument list instead.
    @Query(
        value = "SELECT * FROM billing_invoice WHERE status = :status",
        nativeQuery = true
    )
    Invoice findByStatusNative(String status);
}

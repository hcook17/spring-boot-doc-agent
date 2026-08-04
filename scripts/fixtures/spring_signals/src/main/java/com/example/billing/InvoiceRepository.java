package com.example.billing;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;

class QueryConstants {
    static final boolean NATIVE = true;
}

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

    // Same-line string concat — order by (line, column) (P0.5).
    @Query(value = "SELECT a " + "FROM billing_invoice a", nativeQuery = true)
    java.util.List<Object> findSameLineNative();

    // Compile-time constant nativeQuery (P0.4) — must stay native, not JPQL.
    @Query(value = "SELECT 1", nativeQuery = QueryConstants.NATIVE)
    int nativeConst();
}

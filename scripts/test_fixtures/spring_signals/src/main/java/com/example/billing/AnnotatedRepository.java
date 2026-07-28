package com.example.billing;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

// Regression guard: same annotation-adjacency problem as PaymentLedger.java,
// but for persistence__repository. A literal
// "public interface $NAME extends JpaRepository<$E, $I> {$$$}" pattern
// stopped matching the moment @Repository preceded the interface — which
// is the common case in real code (Spring Data doesn't require the
// annotation, but most teams add it anyway).
@Repository
public interface AnnotatedRepository extends JpaRepository<Invoice, Long> {
}

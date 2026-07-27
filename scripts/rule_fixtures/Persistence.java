package com.example.fixtures;

import javax.persistence.Entity;

@Entity
@Table(name = "billing_invoice")
public class Invoice {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "amount_cents", nullable = false)
    private Long amountCents;

    @Column
    private String memo;

    @ManyToOne
    @JoinColumn(name = "customer_id")
    private Customer customer;

    @OneToMany(mappedBy = "invoice")
    private java.util.List<LineItem> lines;
}

@Repository
interface InvoiceRepository extends JpaRepository<Invoice, Long> {
    @Query(value = "SELECT * FROM billing_invoice", nativeQuery = true)
    java.util.List<Invoice> raw();
}

class InvoiceWriter {
    @Transactional
    public void markPaid(Long id) { }

    @Transactional(readOnly = true)
    public Invoice read(Long id) { return null; }
}

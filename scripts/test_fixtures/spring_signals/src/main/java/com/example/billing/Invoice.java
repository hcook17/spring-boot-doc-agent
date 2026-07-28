package com.example.billing;

import jakarta.persistence.*;

@Entity
@Table(name = "billing_invoice")
public class Invoice {
    @Id
    private Long id;

    @Column(name = "status_code", nullable = false)
    private String status;

    @ManyToOne
    @JoinColumn(name = "customer_id")
    private Customer customer;

    @OneToMany(mappedBy = "invoice")
    private java.util.List<LineItem> lines;
}

class Customer {
}

class LineItem {
}

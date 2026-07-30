package com.example.billing;

import jakarta.persistence.*;

@Entity
@Table(name = "billing_invoice")
public class Invoice {
    @Id
    private Long id;
    private String status;
}

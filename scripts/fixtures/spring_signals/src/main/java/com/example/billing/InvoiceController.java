package com.example.billing;

import org.springframework.web.bind.annotation.*;
import org.springframework.security.access.prepost.PreAuthorize;

@RestController
@RequestMapping("/api/invoices")
public class InvoiceController {

    @GetMapping("/{id}")
    @PreAuthorize(
        "hasRole('BILLING_READ')"
    )
    public String getInvoice(@PathVariable String id) {
        return id;
    }

    @PostMapping
    public String createInvoice() {
        return "created";
    }
}

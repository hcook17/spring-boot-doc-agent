package com.example.billing;

import org.springframework.transaction.annotation.Transactional;

class InvoiceService {
    @Transactional
    public void markPaid(Long id) { }

    @Transactional(readOnly = true)
    public Invoice read(Long id) { return null; }
}

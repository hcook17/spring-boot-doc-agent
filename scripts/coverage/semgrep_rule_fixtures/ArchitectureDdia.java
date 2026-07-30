package com.example.fixtures;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.client.RestTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.kafka.annotation.KafkaListener;
import jakarta.persistence.Entity;
import jakarta.persistence.Version;
import java.sql.Connection;
import java.util.List;

@Entity
class UnversionedLedger {
    private Long id;
    private String amount;
}

@Entity
class VersionedLedger {
    private Long id;

    @Version
    private Long version;
}

class BatchAndStreamDuality {
    @Scheduled(fixedRate = 60000)
    void reconcileNightly() {
    }

    @KafkaListener(topics = "orders")
    void onOrder(String payload) {
    }
}

class RawSqlConcat {
    void run(Connection conn, String tenantId) throws Exception {
        conn.createStatement().executeQuery("SELECT * FROM orders WHERE tenant = '" + tenantId + "'");
    }
}

class OutboundClient {
    RestTemplate template = new RestTemplate();
}

class InvoiceController {
    private InvoiceRepository repo;

    @GetMapping("/invoices")
    List<Invoice> all() {
        return repo.findAll();
    }
}

interface InvoiceRepository {
    List<Invoice> findAll();
}

class Invoice {
}

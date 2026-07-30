package com.example.fixtures.negative;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.client.RestTemplate;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import jakarta.persistence.Entity;
import jakarta.persistence.Version;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.util.List;

/** Negative corpus: shapes that must NOT fire architecture_ddia rules. */
@Entity
class VersionedAccount {
    private Long id;

    @Version
    private Long version;
}

class ScheduledOnlyWorker {
    @Scheduled(fixedRate = 60000)
    void tick() {
    }
}

class KafkaOnlyConsumer {
    @KafkaListener(topics = "orders")
    void onOrder(String payload) {
    }
}

class ParameterizedSql {
    void run(Connection conn, String tenantId) throws Exception {
        PreparedStatement ps = conn.prepareStatement(
            "SELECT * FROM orders WHERE tenant = ?");
        ps.setString(1, tenantId);
        ps.executeQuery();
    }

    void jdbc(JdbcTemplate jdbc, String tenantId) {
        jdbc.query("SELECT * FROM orders WHERE tenant = ?", rs -> {
        }, tenantId);
    }
}

class TimedOutboundClient {
    RestTemplate template = new RestTemplate(new SimpleClientHttpRequestFactory());
}

class PagedInvoiceController {
    private InvoiceRepository repo;

    @GetMapping("/invoices")
    Page<Invoice> all(Pageable pageable) {
        return repo.findAll(pageable);
    }
}

interface InvoiceRepository {
    Page<Invoice> findAll(Pageable pageable);
    List<Invoice> findAll();
}

class Invoice {
}

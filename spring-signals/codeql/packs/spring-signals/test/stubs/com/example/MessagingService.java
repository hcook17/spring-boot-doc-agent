package com.example;

import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.core.KafkaTemplate;

public class MessagingService {
    private final KafkaTemplate<String, String> kafkaTemplate;

    public MessagingService(KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    @KafkaListener(topics = "orders")
    public void handleOrder(String order) {}
}

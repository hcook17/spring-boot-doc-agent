package com.example.fixtures;

import org.springframework.kafka.core.KafkaTemplate;

public class Messaging {
    private KafkaTemplate<String, String> template;

    @KafkaListener(topics = "orders")
    public void onOrder(String payload) { }

    @JmsListener
    public void onJms(String payload) { }
}

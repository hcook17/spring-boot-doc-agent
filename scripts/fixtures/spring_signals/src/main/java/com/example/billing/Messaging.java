package com.example.billing;

import org.springframework.kafka.core.KafkaOperations;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.kafka.annotation.KafkaListener;

class Messaging {
    // ParameterizedType — CodeQL must erase before FQN match (P0.1).
    private KafkaTemplate<String, String> kafkaTemplate;
    // Interface injection — needs source-supertype closure (P0.1).
    private KafkaOperations<String, String> kafkaOperations;
    private JmsTemplate jmsTemplate;

    @KafkaListener(topics = "orders")
    public void onOrder(String payload) { }

    @JmsListener(destination = "orders")
    public void onJms(String payload) { }
}

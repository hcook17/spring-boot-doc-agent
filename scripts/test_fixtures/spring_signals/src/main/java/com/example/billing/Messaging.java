package com.example.billing;

import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.core.KafkaTemplate;

class Messaging {
    private KafkaTemplate<String, String> kafkaTemplate;
    private JmsTemplate jmsTemplate;

    @KafkaListener(topics = "orders")
    public void onOrder(String payload) { }

    @JmsListener(destination = "orders")
    public void onJms(String payload) { }
}

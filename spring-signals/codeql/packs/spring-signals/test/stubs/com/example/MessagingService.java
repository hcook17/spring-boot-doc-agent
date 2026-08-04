package com.example;

import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.core.KafkaOperations;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.amqp.core.AmqpTemplate;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.core.JmsOperations;
import org.springframework.pulsar.annotation.PulsarListener;
import org.springframework.pulsar.core.PulsarTemplate;
import io.awspring.cloud.sqs.annotation.SqsListener;
import io.awspring.cloud.sqs.operations.SqsTemplate;
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.cloud.stream.function.StreamBridge;

public class MessagingService {
    private final KafkaTemplate<String, String> kafkaTemplate;
    private final KafkaOperations<String, String> kafkaOperations;
    private final RabbitTemplate rabbitTemplate;
    private final AmqpTemplate amqpTemplate;
    private final JmsOperations jmsOperations;
    private final PulsarTemplate<String> pulsarTemplate;
    private final SqsTemplate<String> sqsTemplate;
    private final SimpMessagingTemplate simpMessagingTemplate;
    private final StreamBridge streamBridge;

    public MessagingService(
        KafkaTemplate<String, String> kafkaTemplate,
        KafkaOperations<String, String> kafkaOperations,
        RabbitTemplate rabbitTemplate,
        AmqpTemplate amqpTemplate,
        JmsOperations jmsOperations,
        PulsarTemplate<String> pulsarTemplate,
        SqsTemplate<String> sqsTemplate,
        SimpMessagingTemplate simpMessagingTemplate,
        StreamBridge streamBridge
    ) {
        this.kafkaTemplate = kafkaTemplate;
        this.kafkaOperations = kafkaOperations;
        this.rabbitTemplate = rabbitTemplate;
        this.amqpTemplate = amqpTemplate;
        this.jmsOperations = jmsOperations;
        this.pulsarTemplate = pulsarTemplate;
        this.sqsTemplate = sqsTemplate;
        this.simpMessagingTemplate = simpMessagingTemplate;
        this.streamBridge = streamBridge;
    }

    @KafkaListener(topics = "orders")
    public void handleOrder(String order) {}

    @KafkaListener(topics = { "events", "audit" })
    public void handleEvents(String event) {}

    @RabbitListener(queues = "queue1")
    public void handleRabbit(String msg) {}

    @JmsListener(destination = "topic1")
    public void handleJms(String msg) {}

    @PulsarListener(topics = "pulsar-topic")
    public void handlePulsar(String msg) {}

    @SqsListener("sqs-queue")
    public void handleSqs(String msg) {}
}

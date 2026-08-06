package com.example.fixture;

import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.kafka.core.KafkaOperations;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Component;

@Component
public class MessagingFixture {

  /** Parameterized type: the P0 that made the old rule dead code. */
  private KafkaTemplate<String, String> kafka;

  /**
   * Interface-typed injection. The most-specific guard must NOT suppress this:
   * KafkaOperations is the only catalogued match here, so one row is correct.
   * The kafka field above is the opposite direction, where both match and only
   * the impl should survive.
   */
  private KafkaOperations<String, String> kafkaOps;

  private RabbitTemplate rabbit;
  private JmsTemplate jms;

  @KafkaListener(topics = "book-events")
  public void onBook(String payload) {}

  @RabbitListener(queues = "book-queue")
  public void onQueue(String payload) {}
}

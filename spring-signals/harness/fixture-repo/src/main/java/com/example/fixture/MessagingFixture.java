package com.example.fixture;

import org.springframework.kafka.core.KafkaOperations;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Component;

/**
 * Wrong-survivor fixture: the Messaging.ql most-specific-subtype dedup must
 * attribute the interface-typed field to KafkaOperations and the impl-typed
 * field to KafkaTemplate. A count-only assertion cannot catch the two rows
 * swapping signals; expectations/fixture-repo.json pins both survivors.
 */
@Component
public class MessagingFixture {

    private final KafkaOperations<String, String> interfaceOnly;
    private final KafkaTemplate<String, String> implField;

    public MessagingFixture(
            KafkaOperations<String, String> interfaceOnly,
            KafkaTemplate<String, String> implField) {
        this.interfaceOnly = interfaceOnly;
        this.implField = implField;
    }
}

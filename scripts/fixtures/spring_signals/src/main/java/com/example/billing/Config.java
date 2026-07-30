package com.example.billing;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration
class AppConfig {
}

@ConfigurationProperties(prefix = "billing")
class BillingProps {
    @Value("${billing.timeout}")
    private String timeout;
}

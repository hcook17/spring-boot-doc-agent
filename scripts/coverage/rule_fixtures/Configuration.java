package com.example.fixtures;

@ConfigurationProperties(prefix = "billing")
public class BillingProps {
    @Value("${billing.timeout}")
    private String timeout;
}

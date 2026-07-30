package com.example.fixtures;

import org.springframework.web.client.RestTemplate;

@FeignClient(name = "billing")
public interface BillingClient {
    String fetch();
}

class HttpCaller {
    private final RestTemplate restTemplate = new RestTemplate();
}

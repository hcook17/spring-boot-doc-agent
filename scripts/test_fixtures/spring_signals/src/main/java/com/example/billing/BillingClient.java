package com.example.billing;

import org.springframework.cloud.openfeign.FeignClient;

@FeignClient(name = "billing")
interface BillingClient {
    String fetch();
}

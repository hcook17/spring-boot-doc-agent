package com.example.fixture;

import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.reactive.function.client.WebClient;

@Component
public class OutboundFixture {
  private RestTemplate rest;
  private WebClient webClient;

  public RestTemplate rest() {
    return rest;
  }
}

@FeignClient(name = "catalog", url = "https://catalog.example.com")
interface CatalogClient {
  String fetch(String id);
}

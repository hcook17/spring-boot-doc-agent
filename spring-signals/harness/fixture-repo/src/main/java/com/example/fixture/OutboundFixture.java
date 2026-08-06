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

// Positional value= spelling (@AliasFor of name): the detail extraction must
// read it, or the service id is lost for the most common form.
@FeignClient(value = "catalog", url = "https://catalog.example.com")
interface CatalogClient {
  String fetch(String id);
}

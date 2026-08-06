package com.example;

import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.service.annotation.HttpExchange;
import org.springframework.web.service.annotation.GetExchange;
import org.springframework.web.service.annotation.PostExchange;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.client.RestClient;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.web.service.invoker.HttpServiceProxyFactory;
import java.net.http.HttpClient;
import okhttp3.OkHttpClient;

// Positional value= spelling: the most common form, and an @AliasFor of name.
@FeignClient(value = "books", url = "http://example.com")
@HttpExchange("/books")
public interface OutboundClient {
    @GetExchange
    String getBooks();

    @PostExchange
    String createBook(String body);
}

class OutboundUsage {
    private final RestTemplate restTemplate;
    private final RestClient restClient;
    private final WebClient webClient;
    private final RestTemplateBuilder restTemplateBuilder;
    private final HttpServiceProxyFactory httpServiceProxyFactory;
    private final HttpClient javaHttpClient;
    private final OkHttpClient okHttpClient;

    public OutboundUsage(
        RestTemplate restTemplate,
        RestClient restClient,
        WebClient webClient,
        RestTemplateBuilder restTemplateBuilder,
        HttpServiceProxyFactory httpServiceProxyFactory,
        HttpClient javaHttpClient,
        OkHttpClient okHttpClient
    ) {
        this.restTemplate = restTemplate;
        this.restClient = restClient;
        this.webClient = webClient;
        this.restTemplateBuilder = restTemplateBuilder;
        this.httpServiceProxyFactory = httpServiceProxyFactory;
        this.javaHttpClient = javaHttpClient;
        this.okHttpClient = okHttpClient;
    }

    public RestTemplate restTemplateMethod() {
        return restTemplate;
    }
}

package com.example;

import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.PropertySource;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.context.properties.ConfigurationProperties;

@Configuration
@PropertySource("classpath:application.properties")
@ComponentScan(basePackages = "com.example")
public class AppConfig {
    @Value("${app.name:default}")
    private String appName;
}

@ConfigurationProperties(prefix = "app")
class AppProperties {
    private String name;
    private String url;
}

package com.example.fixture;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;

@Configuration
@ComponentScan(basePackages = "com.example.fixture")
@ConfigurationProperties(prefix = "fixture.catalog")
public class ConfigFixture {

  @Value("${fixture.timeout:5000}")
  private int timeout;

  @Value("${fixture.name}")
  private String name;

  @Bean
  public JdbcTemplate jdbcTemplate() {
    return new JdbcTemplate();
  }
}

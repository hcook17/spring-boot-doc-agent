package com.example;

import javax.persistence.EntityManager;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.JdbcOperations;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcOperations;
import org.springframework.transaction.annotation.Transactional;

public class PersistenceService {
    private final JdbcTemplate jdbcTemplate;
    private final NamedParameterJdbcTemplate namedParameterJdbcTemplate;
    private final EntityManager entityManager;

    public PersistenceService(
        JdbcTemplate jdbcTemplate,
        NamedParameterJdbcTemplate namedParameterJdbcTemplate,
        EntityManager entityManager
    ) {
        this.jdbcTemplate = jdbcTemplate;
        this.namedParameterJdbcTemplate = namedParameterJdbcTemplate;
        this.entityManager = entityManager;
    }

    @Transactional
    public void runSql() {
        jdbcTemplate.queryForObject("SELECT * FROM books WHERE id = ?", String.class, 1L);
        jdbcTemplate.queryForList("SELECT jsonb_agg(data) FROM books");
        namedParameterJdbcTemplate.queryForObject("SELECT * FROM books WHERE id = :id", String.class);
        entityManager.createNativeQuery("SELECT * FROM books");
    }
}

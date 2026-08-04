package org.springframework.jdbc.core.namedparam;

import org.springframework.jdbc.core.JdbcOperations;

public class NamedParameterJdbcTemplate implements NamedParameterJdbcOperations {
    public <T> T queryForObject(String sql, Class<T> requiredType) { return null; }
}

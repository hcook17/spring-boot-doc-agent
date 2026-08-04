package org.springframework.jdbc.core;

public class JdbcTemplate implements JdbcOperations {
    public int update(String sql) { return 0; }
    public <T> T queryForObject(String sql, Class<T> requiredType, Object... args) { return null; }
    public <T> java.util.List<T> queryForList(String sql) { return null; }
}

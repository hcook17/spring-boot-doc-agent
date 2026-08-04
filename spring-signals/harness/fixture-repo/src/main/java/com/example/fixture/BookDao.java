package com.example.fixture;

import javax.persistence.EntityManager;
import javax.persistence.PersistenceContext;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Repository
public class BookDao {

  private final JdbcTemplate jdbc;
  private final NamedParameterJdbcTemplate namedJdbc;

  @PersistenceContext private EntityManager em;

  public BookDao(JdbcTemplate jdbc, NamedParameterJdbcTemplate namedJdbc) {
    this.jdbc = jdbc;
    this.namedJdbc = namedJdbc;
  }

  /** propagation is an enum and readOnly a boolean: attr() can read neither. */
  @Transactional(readOnly = true, propagation = Propagation.REQUIRES_NEW)
  public int touch() {
    return jdbc.update("SELECT a " + "FROM content.book WHERE meta ->> 'k' = '1'");
  }

  @Transactional
  public int rename(String t) {
    return namedJdbc.update("UPDATE evolve.book SET title = :t", java.util.Map.of("t", t));
  }

  /** Return type is javax.* -- JakartaMigration claims to cover returns. */
  public EntityManager entityManager() {
    return em;
  }
}

package com.example;

import javax.persistence.EntityManager;
import org.springframework.data.jpa.repository.Query;

public interface BookRepository {
    @Query("SELECT b FROM Book b WHERE b.title = ?1")
    java.util.List<String> findByTitle(String title);

    @Query(value = "SELECT jsonb_agg(data) FROM books WHERE id = ?1", nativeQuery = true)
    String findRawJsonById(Long id);

    EntityManager getEntityManager();
}

package com.example;

import javax.persistence.EntityManager;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.jpa.repository.NativeQuery;
import org.springframework.data.jpa.repository.NativeQueries;
import org.springframework.data.jpa.repository.NamedQueries;
import java.util.List;

public interface BookRepository extends JpaRepository<Book, Long> {
    @Query("SELECT b FROM Book b WHERE b.title = ?1")
    List<String> findByTitle(String title);

    @Query(value = "SELECT jsonb_agg(data) FROM books WHERE id = ?1", nativeQuery = true)
    String findRawJsonById(Long id);

    EntityManager getEntityManager();
}

@javax.persistence.NamedQuery(name = "Book.findAll", query = "SELECT b FROM Book b")
@javax.persistence.NamedNativeQuery(name = "Book.findRaw", query = "SELECT * FROM books WHERE id = ?1")
@javax.persistence.SqlResultSetMapping(name = "BookMapping")
class BookQueries {
}

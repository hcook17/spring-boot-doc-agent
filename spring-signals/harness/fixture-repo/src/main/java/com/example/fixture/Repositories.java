package com.example.fixture;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

interface TopicRepository extends JpaRepository<Book, Long> {

  @Query(value = "SELECT * FROM content.book WHERE meta ->> 'k' = :k", nativeQuery = true)
  java.util.List<Book> findNative(@Param("k") String k);

  @Query("select b from Book b where b.isbn = :isbn")
  Book findJpql(@Param("isbn") String isbn);

  @Modifying
  @Query(value = "UPDATE evolve.book SET title = :t", nativeQuery = true)
  int rename(@Param("t") String t);
}

/** Marker: no methods, no fields. persistence__repository_marker. */
interface BookBasedRepository {}

/** Reaches JpaRepository only transitively -- the P0 the pack claims to fix. */
interface BookBasedTopicRepository extends TopicRepository, BookBasedRepository {}

package com.example.fixture;

import javax.persistence.Column;
import javax.persistence.Entity;
import javax.persistence.GeneratedValue;
import javax.persistence.Id;
import javax.persistence.NamedNativeQueries;
import javax.persistence.NamedNativeQuery;
import javax.persistence.NamedQuery;
import javax.persistence.Table;

@Entity
@Table(name = "book", schema = "content")
@NamedNativeQueries({
  @NamedNativeQuery(name = "Book.byIsbn", query = "SELECT * FROM content.book WHERE isbn = ?"),
  @NamedNativeQuery(name = "Book.byTitle", query = "SELECT * FROM content.book WHERE title = ?")
})
@NamedQuery(name = "Book.all", query = "select b from Book b")
public class Book {
  @Id @GeneratedValue public Long id;

  @Column(name = "isbn_text")
  public String isbn;
}

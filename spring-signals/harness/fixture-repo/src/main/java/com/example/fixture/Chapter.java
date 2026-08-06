package com.example.fixture;

import javax.persistence.Entity;
import javax.persistence.Id;
import javax.persistence.ManyToOne;

/** No @Table: qualifiedTable() must emit "" rather than a bare ".". */
@Entity
public class Chapter {
  @Id public Long id;

  @ManyToOne public Book book;
}

package com.example.fixture;

import javax.persistence.Column;
import javax.persistence.Entity;
import javax.persistence.Id;
import javax.persistence.Table;

/** JPA javax-generation fixture: entity, table, id, and a named column. */
@Entity
@Table(name = "fixture_book")
public class PersistenceFixture {

    @Id
    private Long id;

    @Column(name = "title", nullable = false)
    private String title;
}

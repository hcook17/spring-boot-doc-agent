package com.example;

import javax.persistence.Entity;
import javax.persistence.Table;
import javax.persistence.Id;
import org.springframework.transaction.annotation.Transactional;

@Entity
@Table(name = "books")
public class TestEntity {
    @Id
    private Long id;

    @Transactional(propagation = org.springframework.transaction.annotation.Propagation.REQUIRES_NEW, readOnly = true)
    public void touch() {}
}

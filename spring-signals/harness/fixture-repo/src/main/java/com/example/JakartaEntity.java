package com.example;

import jakarta.persistence.Entity;
import jakarta.persistence.Table;

@Entity
@Table(name = "jakarta_books")
public class JakartaEntity {
    private jakarta.persistence.EntityManager entityManager;

    public jakarta.persistence.EntityManager getEntityManager() {
        return entityManager;
    }
}

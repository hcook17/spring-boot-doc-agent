package com.example;

import javax.persistence.Entity;
import javax.persistence.Table;
import javax.validation.constraints.NotNull;
import javax.servlet.http.HttpServletResponse;

@Entity
@Table(name = "javax_books")
public class JavaxEntity {
    @NotNull
    private String title;

    private HttpServletResponse response;

    public javax.persistence.EntityManager getEntityManager() {
        return null;
    }
}

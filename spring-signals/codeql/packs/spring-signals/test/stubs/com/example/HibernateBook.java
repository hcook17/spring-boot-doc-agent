package com.example;

import org.hibernate.annotations.Type;
import org.hibernate.annotations.TypeDef;
import org.hibernate.annotations.Where;
import org.hibernate.annotations.Fetch;
import org.hibernate.annotations.GenericGenerator;
import com.vladmihalcea.hibernate.type.json.JsonBinaryType;
import javax.persistence.Entity;
import javax.persistence.Id;

@Entity
@TypeDef(name = "jsonb", typeClass = JsonBinaryType.class)
@GenericGenerator(name = "custom", strategy = "uuid")
public class HibernateBook {
    @Id
    @GenericGenerator(name = "id-gen", strategy = "native")
    private Long id;

    @Type(type = "jsonb")
    private String data;

    @Where(clause = "active = true")
    private String active;

    @Fetch(FetchMode.JOIN)
    private String lazy;
}

class FetchMode {
    public static final String JOIN = "JOIN";
}

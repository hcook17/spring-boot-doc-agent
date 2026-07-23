package com.example.billing;

import jakarta.persistence.Entity;

// No @Table, and an acronym-bearing class name — exercises to_snake_case's
// real Spring/Hibernate default-naming behavior (see spring_signal_scan.py's
// to_snake_case docstring for the full explanation). This maps to "slarule",
// NOT "sla_rule" (the "nicer" acronym-aware guess a naive fix would produce)
// and not the old broken "s_l_a_rule" either — verified against Hibernate's
// actual CamelCaseToUnderscoresNamingStrategy source plus maintainer-confirmed
// examples on Hibernate's own discourse forum, not assumed.
@Entity
public class SLARule {
    private Long id;
}

package com.example.billing;

import jakarta.persistence.*;

// Regression guard: @Entity/@Table with OTHER annotations stacked between
// them and the class declaration. A naive literal ast-grep pattern like
// "@Entity\n@Table(...)\npublic class $NAME {$$$}" stops matching the
// instant anything (here: @EntityListeners, @Cacheable) is inserted in
// that sequence — and real Spring entities carry extra annotations like
// this constantly. See spring_ast_grep_rules.yml's persistence__entity
// rule, which is relational (kind + has) specifically to survive this.
@Entity
@Table(name = "payment_ledger")
@EntityListeners(PaymentLedger.class)
@Cacheable
public class PaymentLedger {
    @Id
    private Long id;
}

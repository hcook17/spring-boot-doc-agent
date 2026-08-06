package com.example.fixture;

import jakarta.annotation.PreDestroy;

/** Already-migrated counterpart: jakarta.* imports are not pending rows. */
public class AlreadyMigratedFixture {

    @PreDestroy
    void teardown() {}
}

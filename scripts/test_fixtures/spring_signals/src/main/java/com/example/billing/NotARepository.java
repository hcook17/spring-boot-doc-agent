package com.example.billing;

// Negative case: lives in a "repository"-style role, named like one, but
// doesn't extend any Spring Data interface — should produce zero
// persistence__repository matches. Guards against detection that keys off
// the filename/directory instead of the actual AST shape. Modeled on a
// real false-positive risk found in production code (a *SqlConstants
// class sitting in a repository/ package).
public final class NotARepository {
    public static final String STATUS_COLUMN = "status";

    private NotARepository() {
    }
}

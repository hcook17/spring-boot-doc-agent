package com.example.fixture;

/**
 * Strict-subtype fixture for Types.qll: Base <- Mid <- Leaf exercises
 * transitive matching, and Base <- Base must NOT match (strict, not
 * reflexive). No Spring types involved, so the oracle is library-independent.
 */
public interface TypeHierarchyFixture {

    interface Base {}

    interface Mid extends Base {}

    class Leaf implements Mid {}
}

package com.example.fixture;

import org.springframework.data.repository.Repository;

/**
 * Project-local repository marker: extends the Spring Data root marker and
 * declares no methods of its own. This is the wave-1b shape in miniature --
 * interfaces extending DomainRepository are only findable through the
 * TRANSITIVE supertype walk, and DomainRepository itself is the marker a
 * one-hop walk would mislabel as a root.
 */
public interface DomainRepository<T> extends Repository<T, Long> {}

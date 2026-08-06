package com.example.fixture;

/** Repository reachable only through the transitive walk (one hop too many). */
public interface RepositoryFixture extends DomainRepository<PersistenceFixture> {}

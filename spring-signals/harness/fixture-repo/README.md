# Local Spring Boot fixture for CodeQL runtime gate

This directory contains a minimal Java project used by the `create-test-db.sh`
wrapper to build a CodeQL database without Artifactory credentials.

It uses local stubs for the Spring/Jakarta APIs instead of downloading real
libraries. The stubs are deliberately thin: they exist only to give the CodeQL
Java extractor the qualified names, annotations, and method-call targets the
spring-signals queries match against.

## Build

```bash
./build.sh
```

This compiles all `src/main/java/**/*.java` files into `build/classes/java/main`.

## Layout

- `src/main/java/com/example/` — representative Spring Boot application classes
  (controllers, services, repositories, entities, config, error handling, etc.)
- `src/main/java/**/` — stubs for Spring, Jakarta, Hibernate, OpenAPI, and other
  libraries referenced by the queries.

## Notes

The stubs are intentionally not runtime-correct. For example, `JdbcTemplate`
implements `JdbcOperations` here so the fixture can exercise the query logic
that distinguishes interface use from concrete use. Do not copy these stubs
into a real application.

/**
 * @name OpenAPI documentation surface
 * @description Swagger 2 (springfox) and OpenAPI 3 (springdoc) annotations,
 *              tagged by generation. ocs-api-service carries both stacks:
 *              148 Swagger 2 sites and 1012 OpenAPI 3 sites, with 4 files using
 *              both. springfox 2.9.2 is hard-incompatible with Boot 3, so the
 *              Swagger 2 rows are a removal backlog, not documentation.
 * @kind table
 * @id spring-signals/openapi-surface
 * @tags migration openapi documentation
 */

import Common

from Measured e, Annotation a, string pkg, string name, string kind, string generation
where
  e = a and
  exists(Annotatable owner | a = getAnEffectiveAnnotation(owner)) and
  isExactly(a, pkg, name) and
  signature("openapi", pkg, name, kind, generation)
select
  e.getPath() as file,
  e.getStartLine() as start_line,
  e.getEndLine() as end_line,
  e.getSourceSet() as source_set,
  schemaVersion() as schema_version,
  "openapi__" + kind as rule_id,
  "openapi" as framework,
  generation,
  pkg + "." + name as signal,
  // `name` added: @Tag and @ApiResponse carry no summary/value/description, so
  // every openapi__tag row emitted an empty detail.
  attrs(a, "summary,value,description,name") as detail

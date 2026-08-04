# rule_id migration — wave 1

`rule_coverage.py` computes the CI denominator from pack rule_ids plus ast-grep
over `scripts/fixtures/spring_signals/`. Removing `RawQueries.ql` and renaming
rule_ids without a same-PR fixture and baseline update **fails CI**. That
conflict is the reason wave 1c specifies a landing mode; see CAMPAIGN.md.

## Removed

| Old | New | Notes |
|---|---|---|
| `raw_queries__query` + `query_kind="native"` | `sql__data_query_native` | |
| `raw_queries__query` + `query_kind="jpql"` | `sql__data_query_jpql` | |

`query_kind` is no longer a column; the distinction moved into `rule_id`.

## Added (no predecessor)

| New rule_id | Query |
|---|---|
| `sql__named_native_query` | NativeSql |
| `sql__named_jpql_query` | NativeSql |
| `sql__jdbc_call` | NativeSql |
| `jakarta__pending_import` / `__pending_annotation` / `__pending_type` | JakartaMigration |
| `jakarta__migrated_import` / `__migrated_annotation` / `__migrated_type` | JakartaMigration |
| `hibernate__custom_type` / `__filter` / `__id_generator` / `__fetch` / `__mapping` / `__auditing` | HibernateTypes |
| `hibernate__legacy_types_library` / `__legacy_types_import` | HibernateTypes |
| `openapi__operation` / `__parameter` / `__tag` / `__schema` / `__content` / `__response` | OpenApiSurface |
| `persistence__repository_marker` | Persistence |
| `api_surface__path_prefix` / `__endpoint` / `__param_binding` | ApiSurface |
| `configuration__typed_binding` / `__value_injection` / `__config_annotation` | Configuration |
| `error__advice_class` / `__handler_method` / `__response_status` / `__throw_site` | ErrorHandling |
| `messaging__client_type` | Messaging |
| `outbound__feign` / `__http_exchange` / `__type_usage` | OutboundClients |

## Renamed

| Old | New |
|---|---|
| `api_surface__mapping` | split into `api_surface__path_prefix` + `api_surface__endpoint` |
| `configuration__properties` | split into `configuration__typed_binding` + `configuration__value_injection` |
| `error_handling__advice` | split into `error__advice_class` + `error__handler_method` |
| `messaging__import`, `outbound_clients__import`, `observability__import`, `testing__import` | dropped in wave 1 queries; import-vs-type-usage double counting is a wave 4 decision |
| `messaging__type_usage` | `messaging__client_type` |
| `outbound_clients__feign` | `outbound__feign` |
| `outbound_clients__type_usage` | `outbound__type_usage` |

## Unchanged (wave 2 queries, still legacy `v0` schema)

`references__*`, `security__*`, `observability__*`, `testing__*`.

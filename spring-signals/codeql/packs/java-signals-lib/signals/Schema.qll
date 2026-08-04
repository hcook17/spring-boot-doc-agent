/**
 * Uniform output schema for all signal queries.
 *
 * THE ROW SCHEMA IS THE PRODUCT. Everything else -- QL, ast-grep rules,
 * semgrep rules, a future python-signals-lib -- is an implementation that
 * emits these eleven columns. Changing this schema is a breaking change for
 * every downstream consumer; adding a rule_id is not.
 *
 *   file            repo-relative path
 *   start_line      1-based
 *   end_line        1-based; equals start_line for point signals
 *   source_set      "main" | "test"
 *   schema_version  "v0" legacy 3-column | "v1" this shape
 *   rule_id         "<domain>__<signal>", stable, additive-only
 *   framework       open string set, defined by the emitting query pack
 *                   (spring-signals uses: spring, jpa, hibernate, openapi, sql,
 *                   jakarta). This library does not enumerate them.
 *   generation      version/namespace axis, see Catalog.qll; "" when not tracked
 *   symbol          code-location identity; the join key; always symbolOf()
 *   signal          what was detected: annotation FQN, type FQN, property key
 *   detail          free payload: query text, path, table, target FQN
 *
 * `symbol` and `signal` were one column in the first draft. That is how
 * Persistence.ql came to emit a class name in one branch and
 * `javax.persistence.Column` in another -- a join key and a payload wearing the
 * same name. See docs/SYMBOLS.md.
 *
 * NativeSql.ql appends two SQL-specific columns (schema_refs, uses_json).
 *
 * `generation` is populated ONLY where it unblocks a burndown metric.
 * A blank generation means "not tracked for this rule", never "unknown".
 */

import java

/**
 * Row schema version. Emitted as a column so a decoder can branch without
 * inspecting column counts.
 *
 *   "v0"  legacy 3-column (file, line, rule_id) -- References/Security/
 *         Observability/Testing until wave 2
 *   "v1"  11-column (this file), plus optional query-specific extras
 *
 * Waves 1 and 2 coexist with both shapes in one pack. Making the decoder
 * infer the shape from arity is how a schema migration turns into a silent
 * mis-parse; make it declare itself.
 */
string schemaVersion() { result = "v1" }

/**
 * Gets the stable identity of `e`, in the SCIP-inspired grammar documented in
 * docs/SYMBOLS.md.
 *
 *   type       com.example.pkg/ClassName#
 *   method     com.example.pkg/ClassName#methodName().
 *   field      com.example.pkg/ClassName#fieldName.
 *   parameter  com.example.pkg/ClassName#methodName().(paramName)
 *
 * Every query MUST route `symbol` through this predicate. The eleven-column join
 * is on (file, symbol, rule_id); if three emitters invent three symbol strings
 * the join silently degrades to (file, rule_id) and the whole comparison is
 * worthless. Overloads collapse -- arity is deliberately omitted -- see
 * docs/SYMBOLS.md for why and what it costs.
 *
 * TOTALITY IS LOAD-BEARING AND WAS GOT WRONG ONCE. The first version resolved
 * annotations only when the annotated element was a `RefType`, and resolved
 * imports not at all. Since `sym(e)` appears in every `select`, a missing result
 * DELETES THE ROW rather than blanking a column -- so annotations on methods,
 * fields and parameters (most of the pack) and all ~297 JakartaMigration import
 * rows would have silently vanished. This is precisely the failure mode called
 * out for `attr()` and `tableNameOf` elsewhere in this file, reproduced in the
 * helper that guards every query.
 *
 * The three-tier structure below is therefore deliberate and exhaustive:
 * declaration -> owning declaration -> file. The last tier can never fail, so
 * `symbolOf` is total for any `Element` with a file. Do not add a branch that
 * can return no result.
 */
string symbolOf(Element e) {
  result = declSymbol(e)
  or
  not exists(declSymbol(e)) and result = min(string s | s = ownerSymbol(e) | s)
  or
  not exists(declSymbol(e)) and
  not exists(ownerSymbol(e)) and
  result = e.getFile().getRelativePath() + "#"
}

/**
 * Gets the symbol of a *declaration* -- type, method, constructor, field,
 * parameter, local.
 */
private string declSymbol(Element e) {
  exists(RefType t | t = e | result = typeSymbol(t))
  or
  exists(Method m | m = e | result = typeSymbol(m.getDeclaringType()) + m.getName() + "().")
  or
  exists(Constructor c | c = e | result = typeSymbol(c.getDeclaringType()) + "<init>().")
  or
  exists(Field f | f = e | result = typeSymbol(f.getDeclaringType()) + f.getName() + ".")
  or
  exists(Parameter p | p = e | result = declSymbol(p.getCallable()) + "(" + p.getName() + ")")
  or
  exists(LocalVariableDecl v | v = e | result = declSymbol(v.getCallable()) + "(" + v.getName() + ")")
}

/**
 * Gets the symbol of the declaration that *owns* a non-declaration element.
 *
 * The annotation case is the one that matters. Roughly 25 of the pack's 33
 * binding sites bind `e` to an `Annotation`, so if annotations do not resolve,
 * most of the pack emits nothing.
 */
private string ownerSymbol(Element e) {
  exists(Annotatable owner | owner = e.(Annotation).getAnnotatedElement() |
    result = declSymbol(owner)
  )
  or
  exists(Callable c | c = e.(Expr).getEnclosingCallable() | result = declSymbol(c))
  or
  exists(Callable c | c = e.(Stmt).getEnclosingCallable() | result = declSymbol(c))
}

/** Gets the SCIP-style prefix for a type: `package/TypeName#`. */
private string typeSymbol(RefType t) {
  result = t.getSourceDeclaration().getPackage().getName() + "/" +
      t.getSourceDeclaration().getNestedName() + "#"
}

/**
 * Holds if `f` is build output or annotation-processor output rather than
 * hand-written source.
 *
 * ocs-api-service has no annotation processors today, so this is currently a
 * no-op there. It is not a no-op for any repo with MapStruct, Querydsl, or
 * protobuf, and leaving it out silently inflates CodeQL's counts relative to
 * a filesystem-walking tool like ast-grep. Keep it.
 */
predicate generatedFile(File f) {
  f.getRelativePath().matches("build/%") or
  f.getRelativePath().matches("target/%") or
  f.getRelativePath().matches("%/build/%") or
  f.getRelativePath().matches("%/target/%") or
  f.getRelativePath().matches("%/generated/%") or
  f.getRelativePath().matches("%/generated-sources/%")
}

/**
 * Gets "main" or "test" for a first-party Java source file.
 *
 * The optional leading `(?:.*/)?` tolerates multi-module layouts; ocs-api-service
 * is single-module but the shared harness runs against sibling services that
 * are not.
 *
 * Has no result for library classes, generated code, or anything outside a
 * conventional source set -- which is the filtering mechanism. This replaces
 * the old per-query `isJavaSource`, which matched any `.java` path and so
 * could not distinguish production code from test fixtures or generated code.
 */
string sourceSetOf(File f) {
  not generatedFile(f) and
  result = f.getRelativePath().regexpCapture("^(?:.*/)?src/(main|test)/java/.*\\.java$", 1)
}

/** An element in first-party Java source, in a known source set. */
class Measured extends Element {
  Measured() { exists(sourceSetOf(this.getFile())) }

  string getSourceSet() { result = sourceSetOf(this.getFile()) }

  string getPath() { result = this.getFile().getRelativePath() }

  int getStartLine() { result = this.getLocation().getStartLine() }

  int getEndLine() { result = this.getLocation().getEndLine() }
}

/**
 * Gets a printable string for a compile-time constant expression.
 *
 * Use this instead of `.(StringLiteral).getValue()`. Annotation attributes are
 * routinely constant references rather than literals -- ocs-api-service has
 * `@Async(ThreadPoolConfig.BACKGROUND_TASK_EXECUTOR)` -- and a StringLiteral
 * cast silently drops those rows.
 */
string constantString(Expr e) { result = e.(CompileTimeConstantExpr).getStringValue() }

/** Gets a printable string for a compile-time boolean constant. */
boolean constantBoolean(Expr e) { result = e.(CompileTimeConstantExpr).getBooleanValue() }

/**
 * Gets the concatenated text of a string-valued expression, joining the parts
 * of a `+` chain in source order.
 *
 * Ordering is by (line, column), not line alone. Line-only ordering is
 * nondeterministic when two literals share a line, which is the default
 * formatting for `"SELECT a " + "FROM b"` in most codebases. It happens to be
 * safe in ocs-api-service because Spotless breaks one literal per line, but
 * that is a formatting accident, not a guarantee.
 */
string concatenatedText(Expr root) {
  result =
    concat(StringLiteral lit, int ln, int col |
      lit = root.getAChildExpr*() and
      ln = lit.getLocation().getStartLine() and
      col = lit.getLocation().getStartColumn()
    |
      lit.getValue(), "" order by ln, col
    )
}

/** Collapses runs of whitespace so reconstructed SQL/JPQL diffs cleanly. */
bindingset[s]
string normalizeWhitespace(string s) { result = s.regexpReplaceAll("\\s+", " ").trim() }

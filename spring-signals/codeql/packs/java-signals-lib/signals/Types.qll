/**
 * Type matching that survives generics and inheritance.
 *
 * The original pack matched declared types with bare `hasQualifiedName`. That
 * is correct only for a non-generic type referenced by its exact class. Two
 * failure modes followed:
 *
 *  - `KafkaTemplate<String, Event>` is a ParameterizedType whose name carries
 *    type arguments, so it never matched. `Persistence.ql` avoided this with
 *    `.getErasure()`; `Messaging.ql` and `OutboundClients.ql` did not. The
 *    Messaging rule was dead code. In ocs-api-service the same shape appears as
 *    `RedisTemplate<String, String>` in CachingConfig.
 *
 *  - `interface BookBasedTopicRepository extends TopicRepository,
 *    BookBasedRepository` never reaches `CrudRepository` in one hop. The
 *    non-transitive `getASupertype()` in Persistence.ql misses four
 *    repositories in ocs-api-service.
 *
 * Everything here goes through `getSourceDeclaration()` (which maps a
 * ParameterizedType back to its generic declaration) and a reflexive-transitive
 * supertype walk.
 */

import java

/** Gets the generic source declaration of `t`, or `t` itself if not generic. */
RefType sourceDeclOf(Type t) { result = t.(RefType).getSourceDeclaration() }

/** Holds if `t`, ignoring type arguments, is exactly `pkg.name`. */
predicate typeIs(Type t, string pkg, string name) {
  sourceDeclOf(t).hasQualifiedName(pkg, name)
}

/**
 * Holds if `t`, ignoring type arguments, is `pkg.name` or any subtype of it.
 *
 * Use this for injected collaborators. Enterprise code injects the interface
 * (`AmqpTemplate`, `KafkaOperations`, `JdbcOperations`) or a project-local
 * subclass at least as often as the concrete Spring class.
 */
predicate typeIsOrExtends(Type t, string pkg, string name) {
  exists(RefType sup |
    sup = sourceDeclOf(t).getASourceSupertype*() and
    sup.hasQualifiedName(pkg, name)
  )
}

/** Holds if `t`'s package, ignoring type arguments, matches `pattern`. */
bindingset[pattern]
predicate typePackageMatches(Type t, string pattern) {
  sourceDeclOf(t).getPackage().getName().regexpMatch(pattern)
}

/** Gets the erased simple name of `t`, for the `symbol`/`detail` columns. */
string typeName(Type t) { result = sourceDeclOf(t).getName() }

/** Gets the erased fully-qualified name of `t`. */
string typeFqn(Type t) {
  result = sourceDeclOf(t).getPackage().getName() + "." + sourceDeclOf(t).getName()
}

/**
 * Gets the `i`th type argument of the nearest parameterized supertype of `t`
 * whose source declaration is `pkg.name`.
 *
 * Needed because `BookBasedTopicRepository` binds its entity type on
 * `TopicRepository`, not on the `CrudRepository` it ultimately extends.
 */
Type boundTypeArgument(RefType t, string pkg, string name, int i) {
  exists(ParameterizedType p |
    p = t.getASupertype*() and
    p.getSourceDeclaration().hasQualifiedName(pkg, name) and
    result = p.getTypeArgument(i)
  )
}

/**
 * Holds if `subPkg`.`subName` is a STRICT subtype of `superPkg`.`superName`.
 *
 * Catalogues may list both an interface and its implementation on purpose,
 * because enterprise code injects either. `typeIsOrExtends` then matches BOTH
 * for one site, and since `signal` is the only column that differs the result
 * is two rows sharing a `(file, symbol, rule_id)` join key -- a collision on
 * the trio Schema.qll declares as the contract.
 *
 * Today's catalogues contain exactly one comparable pair
 * (KafkaTemplate/KafkaOperations, RabbitTemplate/AmqpTemplate in
 * Messaging.ql's local catalogue); the SQL executor catalogue is deliberately
 * concrete-only, so the guard is preventive there rather than load-bearing.
 * `Messaging.ql` originally solved this by hand, writing
 * `not typeIsOrExtends(t, ..., "KafkaTemplate")` into the `KafkaOperations`
 * branch. That is correct but quadratic in maintenance: every type added to a
 * catalogue must be excluded from each of its supertypes' branches, and a
 * forgotten exclusion fails silently by emitting a duplicate rather than an
 * error. This derives the same thing from the type hierarchy.
 *
 * Uses `getNestedName()`, not `getName()`. A nested catalogued type would
 * otherwise fail to match here while matching everywhere else -- and the failure
 * mode is "guard does not fire", i.e. the fan-out silently returns.
 *
 * All parameters are bound: this is only ever called with a pair of catalogue
 * entries, never used to enumerate the subtype relation.
 */
bindingset[subPkg, subName, superPkg, superName]
predicate typeStrictlyExtends(string subPkg, string subName, string superPkg, string superName) {
  exists(RefType sub |
    sub.getPackage().getName() = subPkg and
    sub.getNestedName() = subName and
    exists(RefType sup |
      sup = sub.getASourceSupertype+() and
      sup.getPackage().getName() = superPkg and
      sup.getNestedName() = superName
    )
  )
}

/**
 * Holds if the dotted FQN `subFqn` is a strict subtype of `superFqn`.
 *
 * String form of `typeStrictlyExtends`, for catalogues carrying a single FQN per
 * entry rather than a (pkg, name) pair.
 */
bindingset[subFqn, superFqn]
predicate typeStrictlyExtendsFqn(string subFqn, string superFqn) {
  typeStrictlyExtends(fqnPackage(subFqn), fqnSimpleName(subFqn), fqnPackage(superFqn),
    fqnSimpleName(superFqn))
}

/**
 * Gets the package part of a dotted FQN.
 *
 * Splits at the LAST dot, so a nested type spelled `pkg.Outer.Inner` yields
 * package `pkg.Outer`. Every catalogue entry today is a top-level type, so this
 * is exact; if a nested type is ever catalogued, use the (pkg, name) form of
 * `typeStrictlyExtends` with `getNestedName()` instead of this string split.
 */
bindingset[fqn]
private string fqnPackage(string fqn) { result = fqn.regexpCapture("^(.*)\\.[^.]+$", 1) }

/** Gets the simple-name part of a dotted FQN. See `fqnPackage` on nested types. */
bindingset[fqn]
private string fqnSimpleName(string fqn) { result = fqn.regexpCapture("^.*\\.([^.]+)$", 1) }

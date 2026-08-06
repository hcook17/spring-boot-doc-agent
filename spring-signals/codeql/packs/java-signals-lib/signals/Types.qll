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

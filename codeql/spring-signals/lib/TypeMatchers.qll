/**
 * Erasure + source-supertype matchers for Spring type inventories.
 *
 * ParameterizedType (e.g. KafkaTemplate<String, Event>) must be erased
 * before FQN match; interface injection (KafkaOperations) and subclasses
 * need reflexive source-supertype closure.
 */

import java

/**
 * Holds if the erasure of `t`, or any of its source supertypes (reflexive),
 * has qualified name `pkg.name`.
 */
predicate erasureOrSourceSupertypeHasName(RefType t, string pkg, string name) {
  exists(RefType s |
    s = t.getErasure().(RefType).getASourceSupertype*() and
    s.hasQualifiedName(pkg, name)
  )
}

/**
 * Annotation attribute `name` evaluates to compile-time constant string `value`.
 * Covers StringLiteral and constant field references (Tables.FOO).
 */
predicate annotationStringValue(Annotation ann, string name, string value) {
  value = ann.getValue(name).(CompileTimeConstantExpr).getStringValue()
}

/**
 * Annotation attribute `name` is the boolean compile-time constant `true`.
 * Covers BooleanLiteral and static final boolean fields (Constants.NATIVE).
 */
predicate annotationBooleanTrue(Annotation ann, string name) {
  ann.getValue(name).(BooleanLiteral).getBooleanValue() = true
  or
  exists(Field f |
    ann.getValue(name) = f.getAnAccess() and
    f.isStatic() and
    f.isFinal() and
    f.getInitializer().(BooleanLiteral).getBooleanValue() = true
  )
}

import Common

/** Pair that should be reported by the strict-subtype predicates. */
predicate expectedPair(string sub, string supName) {
  sub = "InterfaceB" and supName = "InterfaceA"
  or
  sub = "BaseClass" and supName = "InterfaceA"
  or
  // Transitive: DerivedClass reaches InterfaceA via BaseClass and InterfaceB.
  sub = "DerivedClass" and supName = "InterfaceA"
  or
  sub = "DerivedClass" and supName = "BaseClass"
  or
  sub = "DerivedClass" and supName = "InterfaceB"
}

/** Reflexive pairs that must NOT be reported (strict, not reflexive). */
predicate reflexivePair(string sub, string supName) {
  sub = "InterfaceA" and supName = "InterfaceA"
  or
  sub = "InterfaceB" and supName = "InterfaceB"
  or
  sub = "BaseClass" and supName = "BaseClass"
  or
  sub = "DerivedClass" and supName = "DerivedClass"
}

predicate row(string sub, string supName, string tag) {
  expectedPair(sub, supName) and
  (
    typeStrictlyExtends("com.example", sub, "com.example", supName)
    or
    typeStrictlyExtendsFqn("com.example." + sub, "com.example." + supName)
  ) and
  tag = "expected"
  or
  reflexivePair(sub, supName) and
  not typeStrictlyExtends("com.example", sub, "com.example", supName) and
  not typeStrictlyExtendsFqn("com.example." + sub, "com.example." + supName) and
  tag = "not_reflexive"
}

from string sub, string supName, string tag
where row(sub, supName, tag)
select sub, supName, tag

import Common

/** Pair that should be reported by the strict-subtype predicates. */
predicate expectedPair(string sub, string supName) {
  sub = "InterfaceB" and supName = "InterfaceA"
  or
  sub = "BaseClass" and supName = "InterfaceA"
  or
  sub = "DerivedClass" and supName = "BaseClass"
  or
  sub = "DerivedClass" and supName = "InterfaceB"
}

from string sub, string supName
where
  expectedPair(sub, supName) and
  (
    typeStrictlyExtends("com.example", sub, "com.example", supName)
    or
    typeStrictlyExtendsFqn("com.example." + sub, "com.example." + supName)
  )
select sub, supName

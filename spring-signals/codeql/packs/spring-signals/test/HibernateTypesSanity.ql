import Common

from Annotation a
where
  isExactly(a, "org.hibernate.annotations", "Type")
  or
  isExactly(a, "org.hibernate.annotations", "TypeDef")
  or
  isExactly(a, "org.hibernate.annotations", "Where")
  or
  isExactly(a, "org.hibernate.annotations", "Fetch")
  or
  isExactly(a, "org.hibernate.annotations", "GenericGenerator")
select annotationFqn(a), sym(a), attr(a, "name"), attr(a, "type")

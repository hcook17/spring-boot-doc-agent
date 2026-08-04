import Common

private string transactionalDetail(Annotation a) {
  result =
    concat(string s |
      s = "propagation=" + a.getValue("propagation").(FieldAccess).getField().getName()
      or
      constantBoolean(a.getValue("readOnly")) = true and s = "readOnly=true"
      or
      constantBoolean(a.getValue("readOnly")) = false and s = "readOnly=false"
    |
      s, " " order by s
    )
}

from Annotation a
where
  isExactly(a, "javax.persistence", "Entity")
  or
  isExactly(a, "javax.persistence", "Table")
  or
  isExactly(a, "org.springframework.transaction.annotation", "Transactional")
select annotationFqn(a), sym(a), attr(a, "name"), transactionalDetail(a)

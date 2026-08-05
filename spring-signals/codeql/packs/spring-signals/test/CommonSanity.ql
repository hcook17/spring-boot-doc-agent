import Common

from Annotation a, string value, string joined, string fallback
where
  a.getType().hasQualifiedName("com.example", "SanityAnnotation") and
  (
    // All attributes present: attrs() preserves declaration order and joins
    // with "|".
    a.getAnnotatedElement().(Class).hasQualifiedName("com.example", "AnnotatedSanity") and
    value = attr(a, "value") and
    joined = attrs(a, "value,summary,description") and
    fallback = attrFallback(a, "value,summary")
    or
    // value absent: attrFallback() should fall back to the next attribute.
    a.getAnnotatedElement().(Class).hasQualifiedName("com.example", "AnnotatedFallbackSanity") and
    value = attr(a, "value") and
    joined = attrs(a, "value,summary,description") and
    fallback = attrFallback(a, "value,summary")
  )
select value, joined, fallback

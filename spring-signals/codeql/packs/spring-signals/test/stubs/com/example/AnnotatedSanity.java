package com.example;

/** Uses all attributes to test attrs(). */
@SanityAnnotation(value = "V", summary = "S", description = "D")
public class AnnotatedSanity { }

/** Uses only summary/description so value is absent; tests attrFallback(). */
@SanityAnnotation(summary = "S", description = "D")
class AnnotatedFallbackSanity { }

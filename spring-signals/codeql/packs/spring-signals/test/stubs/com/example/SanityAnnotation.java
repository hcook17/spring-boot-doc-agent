package com.example;

import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

/** Annotation with multiple attributes for CommonSanity.ql. */
@Retention(RetentionPolicy.RUNTIME)
public @interface SanityAnnotation {
    String value() default "";
    String summary() default "";
    String description() default "";
}

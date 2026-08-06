package org.springframework.cloud.openfeign;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
public @interface FeignClient {
    // The real @FeignClient has value() as the positional @AliasFor of name();
    // a stub without it cannot reproduce the @FeignClient("svc") spelling.
    String value() default "";
    String name() default "";
    String url() default "";
    String[] basePackages() default {};
}

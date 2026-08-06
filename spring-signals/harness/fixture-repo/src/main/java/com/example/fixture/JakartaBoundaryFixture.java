package com.example.fixture;

import javax.annotation.Nullable;
import javax.annotation.PostConstruct;
import javax.annotation.Resource;

/**
 * Jakarta split-namespace boundary, in one class:
 *
 * <ul>
 *   <li>JSR-250 ({@code @PostConstruct}, {@code @Resource}) relocated to
 *       jakarta.annotation -- these are pending-migration rows.
 *   <li>JSR-305 ({@code @Nullable}, com.google.code.findbugs) has no jakarta
 *       home -- it must NOT appear as pending even though it lives in the
 *       same {@code javax.annotation} package. This is the jsr305Symbol guard.
 * </ul>
 */
public class JakartaBoundaryFixture {

    @Resource(name = "fixtureBean")
    private String wired;

    @Nullable
    public String maybeNull() {
        return null;
    }

    @PostConstruct
    void init() {}
}

package com.example.fixture;

import javax.annotation.Nullable;
import javax.annotation.PostConstruct;
import javax.annotation.Resource;
import javax.validation.Valid;
import javax.validation.constraints.NotNull;
import org.springframework.stereotype.Component;

@Component
public class JakartaFixture {

  /** Fully qualified inline: leaves no Import node at all. */
  private javax.persistence.EntityManager inlineEm;

  /**
   * JSR-305, NOT relocated by Jakarta EE 9 and with no jakarta equivalent.
   * javax.annotation is a split namespace: @PostConstruct and @Resource above
   * moved, this did not. Flagging it manufactures migration work that does not
   * exist, so it must NOT appear in jakarta__pending_*.
   */
  @Nullable private String maybeAbsent;

  @Resource private String resource;

  @NotNull private String required;

  @PostConstruct
  public void init() {}

  public void validate(@Valid String input) {}

  /** Already migrated: jakarta.* side of the burndown. */
  public jakarta.persistence.EntityManager migrated() {
    return null;
  }
}

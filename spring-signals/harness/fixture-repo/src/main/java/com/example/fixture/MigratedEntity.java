package com.example.fixture;

import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

/**
 * The jakarta side of the burndown. Without this the fixture produced ZERO
 * jakarta__migrated_import and ZERO jakarta__migrated_annotation rows, so the
 * numerator of the ratio JakartaMigration.ql exists to compute was untested.
 */
@Entity
@Table(name = "migrated_entity", schema = "content")
public class MigratedEntity {
  @Id public Long id;
}

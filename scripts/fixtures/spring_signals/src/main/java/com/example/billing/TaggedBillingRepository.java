package com.example.billing;

/**
 * Marker-style repo that does not extend JpaRepository directly.
 * CodeQL getASourceSupertype+ must still classify it; ast-grep may not.
 */
public interface TaggedBillingRepository extends BaseBillingRepository {
}

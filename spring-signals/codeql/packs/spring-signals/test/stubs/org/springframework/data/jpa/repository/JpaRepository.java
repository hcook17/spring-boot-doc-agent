package org.springframework.data.jpa.repository;

import org.springframework.data.repository.PagingAndSortingRepository;

public interface JpaRepository<T, ID> extends PagingAndSortingRepository<T, ID> {
}

package javax.persistence;

public interface EntityManager {
    <T> T find(Class<T> entityClass, Object primaryKey);
    javax.persistence.Query createNativeQuery(String sqlString);
}

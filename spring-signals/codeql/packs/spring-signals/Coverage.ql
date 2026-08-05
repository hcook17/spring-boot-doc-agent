/**
 * @name Extraction coverage
 * @description Repo-relative paths of every .java file the extractor placed in
 *              a recognised source set. Consumed by harness/create-db.sh to
 *              compare the database against the filesystem. Excluded from
 *              spring-signals.qls; it emits one column, not the row schema.
 * @kind table
 * @id spring-signals/coverage
 */

import java

from File f
where exists(sourceSetOf(f))
select f.getRelativePath().replaceAll("\\\\", "/") as file

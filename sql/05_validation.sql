SELECT 'customer_duplicate_keys' AS check_name, count(*) AS violations
FROM (SELECT custkey FROM lakehouse.bronze.customer GROUP BY custkey HAVING count(*) > 1)
UNION ALL
SELECT 'orders_duplicate_keys', count(*)
FROM (SELECT orderkey FROM lakehouse.bronze.orders GROUP BY orderkey HAVING count(*) > 1)
UNION ALL
SELECT 'customer_invalid', count(*) FROM lakehouse.bronze.customer
WHERE custkey IS NULL OR custkey <= 0 OR mktsegment IS NULL OR trim(mktsegment) = ''
UNION ALL
SELECT 'orders_invalid', count(*) FROM lakehouse.bronze.orders
WHERE orderkey IS NULL OR orderkey <= 0 OR custkey IS NULL OR custkey <= 0
 OR orderdate IS NULL OR shippriority IS NULL OR shippriority < 0
UNION ALL
SELECT 'lineitem_invalid', count(*) FROM lakehouse.bronze.lineitem
WHERE orderkey IS NULL OR orderkey <= 0 OR extendedprice IS NULL OR extendedprice < 0
 OR NOT is_finite(extendedprice) OR discount IS NULL OR discount < 0 OR discount > 1
 OR NOT is_finite(discount) OR shipdate IS NULL
UNION ALL
SELECT 'orders_orphans', count(*) FROM lakehouse.bronze.orders o
LEFT JOIN lakehouse.bronze.customer c ON o.custkey = c.custkey WHERE c.custkey IS NULL
UNION ALL
SELECT 'lineitem_orphans', count(*) FROM lakehouse.bronze.lineitem l
LEFT JOIN lakehouse.bronze.orders o ON l.orderkey = o.orderkey WHERE o.orderkey IS NULL
UNION ALL
SELECT 'segment_normalization_changes', count(*) FROM lakehouse.bronze.customer
WHERE mktsegment <> upper(trim(mktsegment));

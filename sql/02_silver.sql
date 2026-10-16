CREATE TABLE lakehouse.silver.shipping_order_lines
WITH (format='PARQUET', compression_codec='ZSTD') AS
SELECT l.orderkey, o.orderdate, o.shippriority, l.shipdate,
       l.extendedprice, l.discount,
       l.extendedprice * (1 - l.discount) AS line_revenue,
       c.mktsegment
FROM (
    SELECT custkey, upper(trim(mktsegment)) AS mktsegment
    FROM lakehouse.bronze.customer
) c
JOIN lakehouse.bronze.orders o ON c.custkey = o.custkey
JOIN lakehouse.bronze.lineitem l ON l.orderkey = o.orderkey
WHERE c.mktsegment = 'BUILDING'
  AND o.orderdate < DATE '1995-03-15'
  AND l.shipdate > DATE '1995-03-15';

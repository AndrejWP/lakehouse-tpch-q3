CREATE TABLE lakehouse.gold.shipping_priority
WITH (format='PARQUET', compression_codec='ZSTD') AS
SELECT orderkey, sum(line_revenue) AS revenue, orderdate, shippriority
FROM lakehouse.silver.shipping_order_lines
GROUP BY orderkey, orderdate, shippriority
ORDER BY revenue DESC
LIMIT 10;

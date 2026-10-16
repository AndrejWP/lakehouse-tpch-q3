SELECT mktsegment, count(*) AS customers
FROM lakehouse.bronze.customer GROUP BY mktsegment ORDER BY customers DESC;
SELECT count(*) AS orders FROM lakehouse.bronze.orders;
SELECT orderkey, revenue, orderdate, shippriority
FROM lakehouse.gold.shipping_priority ORDER BY revenue DESC LIMIT 10;

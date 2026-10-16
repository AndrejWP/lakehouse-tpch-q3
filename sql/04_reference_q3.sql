SELECT l.orderkey, sum(l.extendedprice * (1 - l.discount)) AS revenue,
       o.orderdate, o.shippriority
FROM tpch.sf1.customer c
JOIN tpch.sf1.orders o ON c.custkey = o.custkey
JOIN tpch.sf1.lineitem l ON l.orderkey = o.orderkey
WHERE c.mktsegment = 'BUILDING'
  AND o.orderdate < DATE '1995-03-15'
  AND l.shipdate > DATE '1995-03-15'
GROUP BY l.orderkey, o.orderdate, o.shippriority
ORDER BY revenue DESC
LIMIT 10;

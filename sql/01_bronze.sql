DROP TABLE IF EXISTS lakehouse.gold.shipping_priority;
DROP TABLE IF EXISTS lakehouse.silver.shipping_order_lines;
DROP TABLE IF EXISTS lakehouse.bronze.customer;
DROP TABLE IF EXISTS lakehouse.bronze.orders;
DROP TABLE IF EXISTS lakehouse.bronze.lineitem;
CREATE TABLE lakehouse.bronze.customer
WITH (format='PARQUET', compression_codec='ZSTD') AS
SELECT custkey, mktsegment FROM tpch.sf1.customer;
CREATE TABLE lakehouse.bronze.orders
WITH (format='PARQUET', compression_codec='ZSTD') AS
SELECT orderkey, custkey, orderdate, shippriority FROM tpch.sf1.orders;
CREATE TABLE lakehouse.bronze.lineitem
WITH (format='PARQUET', compression_codec='ZSTD') AS
SELECT orderkey, extendedprice, discount, shipdate FROM tpch.sf1.lineitem;

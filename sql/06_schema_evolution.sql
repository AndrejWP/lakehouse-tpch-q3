DROP TABLE IF EXISTS lakehouse.demo.shipping_lines_evolution;
CREATE TABLE lakehouse.demo.shipping_lines_evolution
WITH (format='PARQUET', compression_codec='ZSTD') AS
SELECT * FROM lakehouse.silver.shipping_order_lines ORDER BY orderkey, shipdate LIMIT 100;
DESCRIBE lakehouse.demo.shipping_lines_evolution;
ALTER TABLE lakehouse.demo.shipping_lines_evolution ADD COLUMN analyst_note varchar;
ALTER TABLE lakehouse.demo.shipping_lines_evolution RENAME COLUMN analyst_note TO quality_note;
DESCRIBE lakehouse.demo.shipping_lines_evolution;
SELECT count(*) AS rows, count(quality_note) AS nonnull_notes
FROM lakehouse.demo.shipping_lines_evolution;

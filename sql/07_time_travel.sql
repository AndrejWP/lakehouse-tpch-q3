-- scripts/iceberg_demo.py creates and replaces :snapshot_id with a real bigint.
DROP TABLE IF EXISTS lakehouse.demo.snapshot_example;
CREATE TABLE lakehouse.demo.snapshot_example
WITH (format='PARQUET', compression_codec='ZSTD') AS
SELECT * FROM lakehouse.gold.shipping_priority;
SELECT snapshot_id FROM lakehouse.demo."snapshot_example$snapshots"
ORDER BY committed_at DESC LIMIT 1;
DELETE FROM lakehouse.demo.snapshot_example WHERE orderkey =
 (SELECT min(orderkey) FROM lakehouse.gold.shipping_priority);
SELECT * FROM lakehouse.demo.snapshot_example FOR VERSION AS OF :snapshot_id;
ALTER TABLE lakehouse.demo.snapshot_example EXECUTE rollback_to_snapshot(:snapshot_id);
SELECT * FROM lakehouse.demo.snapshot_example ORDER BY revenue DESC;

-- Silver сохраняет строки связей детали и поставщика после фильтрации
DROP TABLE IF EXISTS iceberg.silver.part_supplier_filtered;
CREATE TABLE iceberg.silver.part_supplier_filtered
WITH (format = 'PARQUET', compression_codec = 'ZSTD') AS
SELECT p.brand, p.type, p.size, ps.suppkey
FROM iceberg.bronze_zstd.partsupp ps
JOIN iceberg.bronze_zstd.part p ON ps.partkey = p.partkey
WHERE p.brand <> 'Brand#45'
  AND p.type NOT LIKE 'MEDIUM POLISHED%'
  AND p.size IN (49, 14, 23, 45, 19, 3, 36, 9)
  AND ps.suppkey NOT IN (
    SELECT s.suppkey
    FROM iceberg.bronze_zstd.supplier s
    WHERE s.comment LIKE '%Customer%Complaints%'
  );

DROP TABLE IF EXISTS iceberg.gold.supplier_counts;
CREATE TABLE iceberg.gold.supplier_counts
WITH (format = 'PARQUET', compression_codec = 'ZSTD') AS
SELECT brand, type, size, count(DISTINCT suppkey) AS supplier_cnt
FROM iceberg.silver.part_supplier_filtered
GROUP BY brand, type, size;

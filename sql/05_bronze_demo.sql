-- пример запроса к Bronze для SQL Lab в Superset
SELECT p.brand, p.type, p.size, ps.suppkey
FROM iceberg.bronze_zstd.part p
JOIN iceberg.bronze_zstd.partsupp ps ON p.partkey = ps.partkey
LIMIT 20;

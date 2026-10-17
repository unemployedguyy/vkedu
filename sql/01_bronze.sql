-- один масштаб для всех наборов, формат и кодек меняются отдельно
CREATE SCHEMA IF NOT EXISTS iceberg.bronze_gzip;
CREATE SCHEMA IF NOT EXISTS iceberg.bronze_zstd;
CREATE SCHEMA IF NOT EXISTS iceberg.bronze_orc;
CREATE SCHEMA IF NOT EXISTS iceberg.silver;
CREATE SCHEMA IF NOT EXISTS iceberg.gold;

DROP TABLE IF EXISTS iceberg.bronze_gzip.part;
CREATE TABLE iceberg.bronze_gzip.part WITH (format = 'PARQUET', compression_codec = 'GZIP') AS
SELECT partkey, brand, type, size FROM tpch.{{TPCH}}.part;

DROP TABLE IF EXISTS iceberg.bronze_gzip.partsupp;
CREATE TABLE iceberg.bronze_gzip.partsupp WITH (format = 'PARQUET', compression_codec = 'GZIP') AS
SELECT partkey, suppkey FROM tpch.{{TPCH}}.partsupp;

DROP TABLE IF EXISTS iceberg.bronze_gzip.supplier;
CREATE TABLE iceberg.bronze_gzip.supplier WITH (format = 'PARQUET', compression_codec = 'GZIP') AS
SELECT suppkey, comment FROM tpch.{{TPCH}}.supplier;

DROP TABLE IF EXISTS iceberg.bronze_zstd.part;
CREATE TABLE iceberg.bronze_zstd.part WITH (format = 'PARQUET', compression_codec = 'ZSTD') AS
SELECT partkey, brand, type, size FROM tpch.{{TPCH}}.part;

DROP TABLE IF EXISTS iceberg.bronze_zstd.partsupp;
CREATE TABLE iceberg.bronze_zstd.partsupp WITH (format = 'PARQUET', compression_codec = 'ZSTD') AS
SELECT partkey, suppkey FROM tpch.{{TPCH}}.partsupp;

DROP TABLE IF EXISTS iceberg.bronze_zstd.supplier;
CREATE TABLE iceberg.bronze_zstd.supplier WITH (format = 'PARQUET', compression_codec = 'ZSTD') AS
SELECT suppkey, comment FROM tpch.{{TPCH}}.supplier;

DROP TABLE IF EXISTS iceberg.bronze_orc.part;
CREATE TABLE iceberg.bronze_orc.part WITH (format = 'ORC', compression_codec = 'ZSTD') AS
SELECT partkey, brand, type, size FROM tpch.{{TPCH}}.part;

DROP TABLE IF EXISTS iceberg.bronze_orc.partsupp;
CREATE TABLE iceberg.bronze_orc.partsupp WITH (format = 'ORC', compression_codec = 'ZSTD') AS
SELECT partkey, suppkey FROM tpch.{{TPCH}}.partsupp;

DROP TABLE IF EXISTS iceberg.bronze_orc.supplier;
CREATE TABLE iceberg.bronze_orc.supplier WITH (format = 'ORC', compression_codec = 'ZSTD') AS
SELECT suppkey, comment FROM tpch.{{TPCH}}.supplier;


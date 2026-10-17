#!/usr/bin/env python3
"""Run the TPC-H Q16 practical through Trino's HTTP protocol."""

import hashlib
import json
import os
from pathlib import Path
import statistics
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
TRINO = os.environ.get("TRINO_URL", "http://127.0.0.1:8080").rstrip("/")
SCALE = os.environ.get("TPCH_SCHEMA", "sf1")
if SCALE not in ("tiny", "sf1", "sf10"):
    raise SystemExit("TPCH_SCHEMA must be tiny, sf1 or sf10")
SCHEMAS = ("bronze_gzip", "bronze_zstd", "bronze_orc")
TABLES = ("part", "partsupp", "supplier")


def request(url, payload=None):
    if payload is not None:
        body = payload.encode("utf-8")
        headers = {"X-Trino-User": "student", "Content-Type": "text/plain"}
    else:
        body = None
        headers = {"X-Trino-User": "student"}
    parts = urlsplit(url)
    if parts.hostname not in ("localhost", "127.0.0.1"):
        base = urlsplit(TRINO)
        url = urlunsplit((parts.scheme, base.netloc, parts.path, parts.query, parts.fragment))
    req = Request(url, data=body, headers=headers)
    try:
        with urlopen(req, timeout=180) as res:
            return json.load(res)
    except HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code}: {exc.read().decode('utf-8', 'replace')}") from exc


def query(sql, collect_limit=20):
    started = time.monotonic()
    page = request(TRINO + "/v1/statement", sql)
    preview, row_count = [], 0
    digest = hashlib.sha256()
    last = page
    while True:
        if "error" in page:
            raise RuntimeError(f"SQL failed:\n{sql[:1200]}\n{json.dumps(page['error'], ensure_ascii=False)}")
        for row in page.get("data", []):
            row_count += 1
            digest.update(json.dumps(row, ensure_ascii=False, separators=(",", ":")).encode())
            digest.update(b"\n")
            if len(preview) < collect_limit:
                preview.append(row)
        last = page
        if not page.get("nextUri"):
            break
        page = request(page["nextUri"])
    duration = round(time.monotonic() - started, 3)
    return {
        "preview": preview, "rows": row_count, "sha256": digest.hexdigest(),
        "seconds": duration, "trino_stats": last.get("stats", {}),
    }


def scalar(sql):
    data = query(sql, 1)["preview"]
    if not data:
        raise RuntimeError("SQL returned no rows: " + sql)
    return data[0][0]


def sql_file(name):
    return (ROOT / "sql" / name).read_text(encoding="utf-8")


def statements(name):
    source = sql_file(name).replace("{{TPCH}}", SCALE)
    # скрипты не содержат строк с точкой с запятой
    return [part.strip() for part in source.split(";") if part.strip()]


def run_statements(name):
    for idx, sql in enumerate(statements(name), 1):
        print(f"  {name} [{idx}]: {sql[:95].replace(chr(10), ' ')}", flush=True)
        query(sql, 0)


def setup():
    print("[1/5] Loading Bronze, Silver and Gold", flush=True)
    run_statements("01_bronze.sql")
    run_statements("02_silver_gold.sql")


def verify():
    print("[2/5] Checking source counts and Q16 equality", flush=True)
    counts = {}
    for name in TABLES:
        baseline = scalar(f"SELECT count(*) FROM tpch.{SCALE}.{name}")
        counted = {schema: scalar(f"SELECT count(*) FROM iceberg.{schema}.{name}") for schema in SCHEMAS}
        if any(value != baseline for value in counted.values()):
            raise AssertionError(f"Bronze count mismatch for {name}: {baseline} vs {counted}")
        counts[name] = {"tpch": baseline, **counted}
    reference = sql_file("03_reference_q16.sql").replace("{{TPCH}}", SCALE).strip().rstrip(";")
    gold = "SELECT brand, type, size, supplier_cnt FROM iceberg.gold.supplier_counts"
    reference_unordered = reference[:reference.upper().rfind("ORDER BY")].rstrip()
    left = scalar(f"SELECT count(*) FROM ({reference_unordered} EXCEPT {gold})")
    right = scalar(f"SELECT count(*) FROM ({gold} EXCEPT {reference_unordered})")
    if left or right:
        raise AssertionError(f"Q16 differs from Gold: missing={left}, extra={right}")
    n_gold = scalar("SELECT count(*) FROM iceberg.gold.supplier_counts")
    if n_gold <= 0:
        raise AssertionError("Gold must not be empty")
    sample = query("SELECT * FROM iceberg.gold.supplier_counts ORDER BY supplier_cnt DESC, brand, type, size LIMIT 5")
    result = {"counts": counts, "q16_gold_equal": True, "missing": left,
              "extra": right, "gold_rows": n_gold, "gold_sample": sample["preview"]}
    print("  PASS: raw Q16 equals Gold, rows:", n_gold, flush=True)
    return result


def bench():
    print("[3/5] Comparing file sizes and query runtimes", flush=True)
    readings = {}
    template = sql_file("04_benchmark_q16.sql").strip().rstrip(";")
    for schema in SCHEMAS:
        tables = {}
        for name in TABLES:
            size = scalar(f'SELECT coalesce(sum(file_size_in_bytes), 0) FROM iceberg.{schema}."{name}$files"')
            tables[name] = int(size)
        text = template.replace("{{BRONZE}}", schema)
        warmup = query(text, 0)
        trials = [query(text, 0) for _ in range(3)]
        if any(t["sha256"] != warmup["sha256"] or t["rows"] != warmup["rows"] for t in trials):
            raise AssertionError("The result changed between runs: " + schema)
        readings[schema] = {
            "data_files_bytes": tables,
            "total_bytes": sum(tables.values()),
            "rows_returned": warmup["rows"],
            "result_sha256": warmup["sha256"],
            "warmup_seconds": warmup["seconds"],
            "runs_seconds": [r["seconds"] for r in trials],
            "mean_seconds": round(statistics.mean(r["seconds"] for r in trials), 3),
        }
        print(f"  {schema}: {readings[schema]['total_bytes']} bytes, mean {readings[schema]['mean_seconds']} s", flush=True)
    if len({v["result_sha256"] for v in readings.values()}) != 1:
        raise AssertionError("Benchmark results differ between variants")
    return readings


def extras():
    print("[4/5] Testing schema evolution and snapshot time travel", flush=True)
    query("DROP TABLE IF EXISTS iceberg.silver.schema_demo", 0)
    query("CREATE TABLE iceberg.silver.schema_demo WITH (format='PARQUET') AS SELECT partkey, brand FROM iceberg.bronze_zstd.part LIMIT 10", 0)
    query("ALTER TABLE iceberg.silver.schema_demo ADD COLUMN notes VARCHAR", 0)
    query("ALTER TABLE iceberg.silver.schema_demo RENAME COLUMN notes TO processing_notes", 0)
    n_null = scalar("SELECT count(*) FROM iceberg.silver.schema_demo WHERE processing_notes IS NULL")
    if n_null != 10:
        raise AssertionError(f"Unexpected schema demo count: {n_null}")

    query("DROP TABLE IF EXISTS iceberg.silver.snapshot_demo", 0)
    query("CREATE TABLE iceberg.silver.snapshot_demo WITH (format='PARQUET') AS SELECT partkey, brand FROM iceberg.bronze_zstd.part LIMIT 10", 0)
    old_id = scalar('SELECT snapshot_id FROM iceberg.silver."snapshot_demo$snapshots" ORDER BY committed_at DESC LIMIT 1')
    query("INSERT INTO iceberg.silver.snapshot_demo VALUES (-1, 'DEMO BRAND')", 0)
    now = scalar("SELECT count(*) FROM iceberg.silver.snapshot_demo")
    earlier = scalar(f"SELECT count(*) FROM iceberg.silver.snapshot_demo FOR VERSION AS OF {int(old_id)}")
    if (earlier, now) != (10, 11):
        raise AssertionError(f"Time travel wrong: past={earlier}, now={now}")
    return {"evolution": "column notes added and renamed processing_notes",
            "old_rows_with_null": n_null, "snapshot_id": old_id,
            "time_travel_before": earlier, "time_travel_after": now}


def render_report(data):
    template = (ROOT / "report.md").read_text(encoding="utf-8")
    def mib(size):
        return f"{size / 1048576:.3f}"
    checks, benchdata, extra = data["checks"], data["benchmark"], data["extras"]
    bronze_rows = []
    for schema, name_format, codec in (("bronze_gzip", "PARQUET", "GZIP"),
                                      ("bronze_zstd", "PARQUET", "ZSTD"),
                                      ("bronze_orc", "ORC", "ZSTD")):
        for name in TABLES:
            bytecount = benchdata[schema]["data_files_bytes"][name]
            num = checks["counts"][name][schema]
            bronze_rows.append(f"| {schema}.{name} | {num} | {mib(bytecount)} | {name_format} | {codec} | нет |")
    silver_rows = scalar("SELECT count(*) FROM iceberg.silver.part_supplier_filtered")
    size_silver = scalar('SELECT coalesce(sum(file_size_in_bytes), 0) FROM iceberg.silver."part_supplier_filtered$files"')
    size_gold = scalar('SELECT coalesce(sum(file_size_in_bytes), 0) FROM iceberg.gold."supplier_counts$files"')
    perf_rows = []
    for schema, fmt, codec in (("bronze_gzip", "Parquet", "GZIP"),
                                ("bronze_zstd", "Parquet", "ZSTD"),
                                ("bronze_orc", "ORC", "ZSTD")):
        d = benchdata[schema]
        perf_rows.append(f"| {fmt} | {codec} | {mib(d['total_bytes'])} | {d['mean_seconds']:.3f} | {d['runs_seconds']} |")
    replacement = {
        "<!-- BRONZE_ROWS -->": "\n".join(bronze_rows),
        "<!-- SILVER_ROW -->": f"| part_supplier_filtered | brand, type, size, suppkey | {silver_rows} | {mib(size_silver)} | PARQUET | ZSTD | нет |",
        "<!-- GOLD_ROW -->": f"| supplier_counts | brand, type, size, supplier_cnt | {checks['gold_rows']} | {mib(size_gold)} | PARQUET | ZSTD | нет |",
        "<!-- PERFORMANCE_ROWS -->": "\n".join(perf_rows),
        "<!-- GOLD_SAMPLE -->": "\n".join(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} |" for r in checks["gold_sample"]),
        "<!-- TIME_TRAVEL -->": f"Снапшот {extra['snapshot_id']}: до INSERT было {extra['time_travel_before']} строк, после INSERT стало {extra['time_travel_after']} строк",
        "<!-- STATUS -->": f"Проверка пройдена: запрос Q16 и Gold совпадают полностью, результат содержит {checks['gold_rows']} строк"
    }
    for a, b in replacement.items():
        template = template.replace(a, b)
    return template


def main():
    action = sys.argv[1] if len(sys.argv) > 1 else "all"
    RESULTS.mkdir(exist_ok=True)
    if action not in ("all", "setup", "verify", "bench", "extras", "report"):
        raise SystemExit("Use: all | setup | verify | bench | extras | report")
    if action == "setup":
        setup()
        return
    if action == "verify":
        print(json.dumps(verify(), ensure_ascii=False, indent=2))
        return
    if action == "bench":
        print(json.dumps(bench(), ensure_ascii=False, indent=2))
        return
    if action == "extras":
        print(json.dumps(extras(), ensure_ascii=False, indent=2))
        return
    if action == "report":
        data = json.loads((RESULTS / "metrics.json").read_text(encoding="utf-8"))
        (ROOT / "report.md").write_text(render_report(data), encoding="utf-8")
        return
    start = time.monotonic()
    setup()
    checks = verify()
    benchmarking = bench()
    extra = extras()
    data = {"tpch_schema": SCALE, "checks": checks, "benchmark": benchmarking, "extras": extra,
            "total_seconds": round(time.monotonic() - start, 2)}
    (RESULTS / "metrics.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    (ROOT / "report.md").write_text(render_report(data), encoding="utf-8")
    print("[5/5] Report and measurements saved", flush=True)


if __name__ == "__main__":
    main()

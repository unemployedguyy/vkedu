from sqlalchemy import create_engine, text

engine = create_engine("trino://student@trino:8080/iceberg/bronze_zstd")
with engine.connect() as connection:
    rows = connection.execute(text("SELECT count(*) FROM iceberg.bronze_zstd.part")).scalar_one()
    sample = connection.execute(text(
        "SELECT brand, size FROM iceberg.bronze_zstd.part ORDER BY partkey LIMIT 3"
    )).fetchall()

assert rows > 0
assert len(sample) == 3
print(f"Superset environment connected to Bronze: {rows} parts")
print("Sample:", sample)

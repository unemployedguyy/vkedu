# Проверка лабораторной

Проверена автоматическим запуском GitHub Actions на Ubuntu 24.04, 17 октября 2026.

## Основная лабораторная

Успешный запуск: https://github.com/unemployedguyy/vkedu/actions/runs/39049502812

- Успешно поднялись MinIO, PostgreSQL, Lakekeeper, Trino 484
- Тестовый источник: TPC-H sf1
- Загружены таблицы part (200 000 строк), partsupp (800 000) и supplier (10 000)
- Построены Bronze, Silver и Gold
- Результаты исходного Q16 и Gold совпали без расхождений (18 314 строк)
- Сравнены Parquet/GZIP, Parquet/ZSTD и ORC/ZSTD
- Проверены schema evolution и time travel

Подробные значения: [metrics.json](metrics.json). Для сравнения указаны суммы физических файлов данных Iceberg, не полный объем хранилища с метаданными.

## Дополнительный BI-инструмент

Проверка Superset ведется отдельно в workflow [Superset Bronze Check](../.github/workflows/bi.yml). Результат выполнения следует смотреть на [странице Actions](https://github.com/unemployedguyy/vkedu/actions/workflows/bi.yml).

Отсутствие скриншота не следует подменять нарисованным примером интерфейса. Проверка чтения Bronze из BI-контейнера выполняется SQL-запросом в [bronze_check.py](../superset/bronze_check.py).

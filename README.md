# VK Education, практическая №1: вариант 4, TPC-H Q16

Небольшой Lakehouse на Docker: MinIO, PostgreSQL, Lakekeeper, Trino, Iceberg и дополнительный Apache Superset. Запрос Q16 считает количество поставщиков по бренду, типу и размеру детали с исключением части деталей и поставщиков с жалобами.

## Структура

- [compose.yaml](compose.yaml) - сервисы
- [sql/01_bronze.sql](sql/01_bronze.sql) - загрузка исходных данных из TPC-H в Iceberg
- [sql/02_silver_gold.sql](sql/02_silver_gold.sql) - очистка и агрегирование
- [sql/03_reference_q16.sql](sql/03_reference_q16.sql) - исходный запрос для проверки
- [sql/04_benchmark_q16.sql](sql/04_benchmark_q16.sql) - один запрос для трех наборов файлов
- [scripts/run.py](scripts/run.py) - проверка правильности, бенчмарк и обновление отчета
- [report.md](report.md) - отчет по форме преподавателя

## Как запустить

Нужны Docker Engine с Compose v2 и Python 3.10+.

~~~bash
docker compose up -d
docker compose ps
python scripts/run.py all
~~~

Используется TPC-H \`sf1\`, как указано в отчете. Если ресурсов мало, для быстрой отладки можно выбрать \`tiny\`:

~~~bash
TPCH_SCHEMA=tiny python scripts/run.py all
~~~

В Windows PowerShell:

~~~powershell
$env:TPCH_SCHEMA = 'tiny'
python scripts/run.py all
~~~

Данные из контейнеров сохраняются в Docker volumes. Повторный запуск скрипта пересоздает аналитические Iceberg-таблицы и измеряет их заново. Чтобы очистить все вместе с данными: \`docker compose down -v\`.

## Проверка

Скрипт выполняет:
1. загрузку трех наборов Bronze: Parquet/GZIP, Parquet/ZSTD, ORC/ZSTD
2. построение Silver и Gold
3. сравнение исходного Q16 и Gold через две операции EXCEPT
4. замер размера данных через Iceberg \`$files\`, прогрев и три запуска запросов
5. изменение схемы и запрос к предыдущему Iceberg-снапшоту
6. запись \`results/metrics.json\` и заполнение \`report.md\`

Если проверка не пройдет, программа завершится с ошибкой. **Наличие файлов в репозитории само по себе не означает успешное выполнение**. Статус проверяется во вкладке Actions.

## Дополнительный инструмент

~~~bash
docker compose --profile bi up -d --build superset
~~~

Откройте \`http://localhost:8088\` (admin / admin123), добавьте Database с URI \`trino://student@trino:8080/iceberg/bronze_zstd\`. Затем откройте SQL Lab и выполните запрос из [sql/05_bronze_demo.sql](sql/05_bronze_demo.sql). Superset намеренно вынесен в отдельный профиль, чтобы не занимать память при тестах в CI.

Сервис Trino доступен на \`http://localhost:8080\`, Lakekeeper на \`http://localhost:8181\`, MinIO Console на \`http://localhost:9001\` (minioadmin / minioadmin123).

## Эксперименты

Масштаб \`sf1\` выбран, чтобы можно было прогнать работу на обычном ноутбуке и ограниченном CI runner. Колонки Bronze: \`part(partkey, brand, type, size)\`, \`partsupp(partkey, suppkey)\`, \`supplier(suppkey, comment)\`. Для Silver и Gold выбран Parquet + ZSTD без партиционирования. Решения объясняются в [отчете](report.md).

## Удаленная проверка

Workflow [lakehouse.yml](.github/workflows/lakehouse.yml) пытается поднять стек на GitHub Actions и запустить полный сценарий. Измерения зависят от конкретного runner, а проверка Superset в UI остается отдельной демонстрацией.

Все пароли в Compose тестовые. Не публикуйте эти контейнеры в открытом интернете.

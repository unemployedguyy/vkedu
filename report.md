# Отчет по практической работе №1

**Тема:** локальный Lakehouse, медальонная архитектура и сравнение кодеков

## 1. Вариант и масштаб

| Поле | Значение |
|---|---|
| ФИО (как в VK Education) | **указать ФИО** |
| Вариант (запрос) | **4, TPC-H Q16 Parts/Supplier Relationship** |
| Масштаб | **sf1** |
| Почему выбрал такой масштаб | sf1 достаточно большой для проверки соединений и группировок, но не требует отдельного сервера. Масштаб одинаковый во всех слоях |

## 2. Поднятые сервисы

| Сервис | Роль | Почему выбрал |
|---|---|---|
| MinIO | S3-совместимое хранение файлов | Локальное объектное хранилище без облачного аккаунта |
| PostgreSQL | Хранение служебных данных Lakekeeper | Поддерживаемая реляционная база, легко запускается в Docker |
| Lakekeeper | Iceberg REST Catalog | Отделяет информацию о таблицах от движка запросов |
| Trino | Выполнение SQL и чтение Iceberg | Может обращаться и к TPC-H, и к Iceberg из одного запроса |
| Superset | BI-интерфейс | Через SQL Lab можно открыть Bronze и построить простой график |

**Развертывание:** все основные сервисы находятся в файле [compose.yaml](compose.yaml).

Команды:

~~~powershell
docker compose up -d
docker compose ps
python scripts/run.py all
docker compose --profile bi build superset
docker compose --profile bi up -d --no-deps superset
~~~

Пример конфигурации каталога Trino, где хранение идет через MinIO:

~~~properties
connector.name=iceberg
iceberg.catalog.type=rest
iceberg.rest-catalog.uri=http://lakekeeper:8181/catalog
iceberg.rest-catalog.warehouse=demo
fs.s3.enabled=true
s3.endpoint=http://minio:9000
s3.path-style-access=true
~~~

## 3. Разбор запроса Q16

Запрос считает количество уникальных поставщиков для сочетаний бренда, типа и размера детали. Сначала исключаются детали бренда Brand#45, типы MEDIUM POLISHED и размеры вне нужного списка. Затем исключаются поставщики с комментариями о жалобах клиентов.

| Таблица TPC-H | Нужные колонки | Использование |
|---|---|---|
| part | partkey, brand, type, size | Связь с partsupp, фильтры по бренду, типу и размеру, группировка |
| partsupp | partkey, suppkey | Связь деталей с поставщиками, подсчет уникальных suppkey |
| supplier | suppkey, comment | Исключение поставщиков с жалобами |

Основной фильтр из запроса:

~~~sql
WHERE p.brand <> 'Brand#45'
  AND p.type NOT LIKE 'MEDIUM POLISHED%'
  AND p.size IN (49, 14, 23, 45, 19, 3, 36, 9)
  AND ps.suppkey NOT IN (
    SELECT suppkey
    FROM tpch.sf1.supplier
    WHERE comment LIKE '%Customer%Complaints%'
  )
~~~

Исходный запрос находится в [sql/03_reference_q16.sql](sql/03_reference_q16.sql).

## 4. Медальонная архитектура

Данные проходят три слоя.

- **Bronze:** копии нужных колонок исходных таблиц без очистки. Для опыта созданы три варианта хранения: Parquet/GZIP, Parquet/ZSTD, ORC/ZSTD.
- **Silver:** деталь соединяется с поставщиком, применяются условия Q16. Таблица `part_supplier_filtered` содержит только нужные для группировки поля.
- **Gold:** таблица `supplier_counts` хранит готовое количество уникальных поставщиков для каждой комбинации `brand, type, size`.

### Bronze

Размером считается сумма размеров **файлов данных Iceberg** по таблице `$files`, без накладных расходов метаданных и PostgreSQL.

| Таблица | Строк | Вес данных, МиБ | Формат | Сжатие | Партиционирование |
|---|---:|---:|---|---|---|
| bronze_gzip.part | 200000 | 0.726 | PARQUET | GZIP | нет |
| bronze_gzip.partsupp | 800000 | 2.234 | PARQUET | GZIP | нет |
| bronze_gzip.supplier | 10000 | 0.140 | PARQUET | GZIP | нет |
| bronze_zstd.part | 200000 | 0.658 | PARQUET | ZSTD | нет |
| bronze_zstd.partsupp | 800000 | 2.148 | PARQUET | ZSTD | нет |
| bronze_zstd.supplier | 10000 | 0.159 | PARQUET | ZSTD | нет |
| bronze_orc.part | 200000 | 0.440 | ORC | ZSTD | нет |
| bronze_orc.partsupp | 800000 | 1.347 | ORC | ZSTD | нет |
| bronze_orc.supplier | 10000 | 0.147 | ORC | ZSTD | нет |

На sf1 сознательно не добавлял партиционирование: объем небольшой, а высокий разброс значений `partkey` создал бы много мелких файлов. Нужные поля оставлены без переименования, чтобы их было легче сравнивать с исходным TPC-H.

### Silver

| Таблица | Колонки | Строк | Вес данных, МиБ | Формат | Сжатие | Партиционирование |
|---|---|---:|---:|---|---|---|
| part_supplier_filtered | brand, type, size, suppkey | 118274 | 0.366 | PARQUET | ZSTD | нет |

На этом слое применены фильтры и соединение таблиц. Оставил Parquet + ZSTD, так как таблица нужна прежде всего для аналитического чтения, а дополнительные копии данных не требуются. Партиционирование не использовал из-за размера sf1.

### Gold

| Таблица | Колонки | Строк | Вес данных, МиБ | Формат | Сжатие | Партиционирование |
|---|---|---:|---:|---|---|---|
| supplier_counts | brand, type, size, supplier_cnt | 18314 | 0.039 | PARQUET | ZSTD | нет |

Gold получен по формуле:

~~~sql
SELECT brand, type, size, count(DISTINCT suppkey) AS supplier_cnt
FROM iceberg.silver.part_supplier_filtered
GROUP BY brand, type, size;
~~~

Результат отсортирован по числу поставщиков, далее по бренду, типу и размеру.

## 5. Проверка результата и производительности

Проверка пройдена: запрос Q16 и Gold совпадают полностью, результат содержит 18314 строк

Проверка устроена через сравнение результата исходного Q16 с Gold в обе стороны операцией `EXCEPT`. Если обе разности пустые, строки совпадают.

Пример первых пяти результатов:

| brand | type | size | supplier_cnt |
|---|---|---:|---:|
| Brand#41 | MEDIUM BRUSHED TIN | 3 | 28 |
| Brand#54 | STANDARD BRUSHED COPPER | 14 | 27 |
| Brand#11 | STANDARD BRUSHED TIN | 23 | 24 |
| Brand#11 | STANDARD BURNISHED BRASS | 36 | 24 |
| Brand#15 | MEDIUM ANODIZED NICKEL | 3 | 24 |

### Формат, кодек и скорость

Размеры измерены по метаданным Iceberg, скорость по полному выполнению запроса через API Trino. Для каждого варианта делается один прогрев и три измерения. Измерения запускались последовательно в одной среде, поэтому результаты лучше сравнивать внутри этого запуска.

| Формат | Сжатие | Размер Bronze, МиБ | Среднее время Q16, с | Три запуска, с |
|---|---|---:|---:|---|
| Parquet | GZIP | 3.100 | 0.770 | [0.732, 0.815, 0.763] |
| Parquet | ZSTD | 2.965 | 0.630 | [0.598, 0.698, 0.594] |
| ORC | ZSTD | 1.934 | 0.616 | [0.6, 0.666, 0.581] |

**Методика:** запрос, фильтры и масштаб данных одинаковые для всех трех наборов. Менялся только формат и кодек записанных файлов. Между запусками не сбрасывались кэши ОС и Trino, поэтому тест не измеряет чистую скорость чтения с диска и не подходит для общего рейтинга форматов. Для более строгого теста нужны дополнительные повторы на выделенной машине и очистка кэшей.

## 6. Часть 2

### 6.1. Понять и объяснить

**Зачем нужен Lakehouse:** объектное хранилище удобно для хранения файлов большого объема, а Iceberg добавляет таблицам метаданные, транзакционные снимки и развитие схемы. При этом Trino выполняет обычные SQL-запросы. Для маленьких данных традиционной БД может быть достаточно, но Lakehouse гибче при работе с разными форматами и независимыми движками обработки.

**Schema evolution:** для отдельной таблицы `silver.schema_demo` добавлена колонка `notes`, затем переименована в `processing_notes`. Старые строки остаются доступными; у них значение новой колонки равно NULL.

~~~sql
ALTER TABLE iceberg.silver.schema_demo ADD COLUMN notes VARCHAR;
ALTER TABLE iceberg.silver.schema_demo RENAME COLUMN notes TO processing_notes;
SELECT count(*) FROM iceberg.silver.schema_demo
WHERE processing_notes IS NULL;
~~~

**Time travel:** Снапшот 6795136987578273271: до INSERT было 10 строк, после INSERT стало 11 строк

~~~sql
SELECT snapshot_id
FROM iceberg.silver."snapshot_demo$snapshots"
ORDER BY committed_at DESC;

SELECT count(*)
FROM iceberg.silver.snapshot_demo
FOR VERSION AS OF <snapshot_id>;
~~~

Здесь `<snapshot_id>` надо заменить реально полученным числом. Сам сценарий выполняется автоматически в [scripts/run.py](scripts/run.py).

### 6.2. Дополнительный инструмент

Выбран **Apache Superset**. Он запускается в Docker отдельно от обязательных компонентов:

~~~powershell
docker compose --profile bi build superset
docker compose --profile bi up -d --no-deps superset
~~~

В интерфейсе по адресу `http://localhost:8088` можно добавить подключение Trino по URI `trino://student@trino:8080/iceberg/bronze_zstd` и в SQL Lab выполнить:

~~~sql
SELECT p.brand, p.type, p.size, ps.suppkey
FROM iceberg.bronze_zstd.part p
JOIN iceberg.bronze_zstd.partsupp ps ON p.partkey = ps.partkey
LIMIT 20;
~~~

Этот запрос демонстрирует чтение Bronze через дополнительный инструмент. **Скриншот интерфейса и подтверждение подключения добавляются после фактического запуска Superset.**

## 7. Выводы

В работе исходные данные TPC-H разделены на Bronze, Silver и Gold. Такое разделение позволяет не смешивать хранение первичных данных и создание конечной аналитики. Сравнение GZIP и ZSTD показывает, как размер файлов и скорость обработки могут отличаться при одном SQL-запросе. Iceberg позволяет менять схему и читать предыдущие снимки таблицы, а Trino дает единый SQL-интерфейс ко всем слоям.

---

**Примечание о проверке:** числовые результаты получены автоматическим запуском GitHub Actions 17.10.2026 на TPC-H sf1. Скриншот Superset еще не подтвержден. Пароли демонстрационные, сервисы предназначены только для локального использования.
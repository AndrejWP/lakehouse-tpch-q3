# Практическая работа №1 — Lakehouse, ELT и TPC-H Q3

## 1. Вариант и масштаб

| Параметр | Значение |
| --- | --- |
| ФИО | Потрикеев Андрей |
| Вариант | №1 — TPC-H Q3 Shipping Priority |
| Масштаб | sf1 |
| Обоснование | Достаточная проекция трёх таблиц для измерений локального IO/сжатия; умеренное потребление RAM и диска на машине 24 ГБ. |
| Фактический запуск | 2026-10-16T18:50:43.609353+00:00 |
| Идентификатор | a2ee78d3-974a-4f3f-9f71-1512dd2785f0 |

## 2. Поднятые сервисы и обоснование

| Сервис | Роль в стеке | Почему выбран |
| --- | --- | --- |
| MinIO | S3 data/metadata files Iceberg | Разделение хранения и вычислений, совместимость S3; локальная FS этого API не даёт. |
| PostgreSQL 16.8 | Метаданные Lakekeeper | Транзакции и поддерживаемый Lakekeeper backend. |
| Lakekeeper 0.9.5 | REST Catalog | Регистрирует таблицы и согласует metadata pointers; отдельные Parquet-файлы каталога не имеют. |
| Trino 479 | TPC-H и SQL ELT | Один движок для source, Iceberg, Parquet/ORC и Q3. |
| Superset 4.1.2 | SQL Lab BI | Проверяемое чтение Bronze и Gold через Trino SQLAlchemy driver. |

Команды: `docker compose up -d --build --wait --wait-timeout 900`, `make bootstrap`, `docker compose ps`, `docker compose down`. MinIO собирается из официальных исходников закреплённого релиза, поскольку загрузка старых registry images завершалась отказом. Volume PostgreSQL сохраняет метаданные, MinIO — файлы, Superset — локальные metadata.

Среда: `{"host_os": "Darwin", "host_architecture": "arm64", "host_python": "3.14.6", "docker_engine": "29.5.3", "docker_architecture": "aarch64", "docker_memory_bytes": 8321515520, "docker_cpus": 10, "trino_heap": "3G", "trino_query_memory": "1500MB", "scale": "sf1"}`.

Локальные проверки: [unit tests](results/unit_tests.json), [SQL/Python/Compose static checks](results/static_checks.json). Это не замена проверке работающих контейнеров.

## 3. Разбор Q3

| Таблица TPC-H | Колонки | Назначение |
| --- | --- | --- |
| customer | custkey, mktsegment | JOIN с orders; фильтр BUILDING |
| orders | orderkey, custkey, orderdate, shippriority | JOIN с customer/lineitem; orderdate < 1995-03-15; группировка и вывод |
| lineitem | orderkey, extendedprice, discount, shipdate | JOIN; shipdate > 1995-03-15; extendedprice*(1-discount), SUM |

LIMIT применяется после агрегации, revenue не округляется. Gold физически не упорядочен; просмотр всегда использует ORDER BY revenue DESC LIMIT 10. Проверка сравнивает ключи, дату, приоритет и revenue с rel_tol=1e-10/abs_tol=1e-6; допускает только корректные пограничные ничьи.

## 4. Medallion

### Bronze

| Таблица | Колонки | Строк | MiB data files | Формат | Сжатие | Партиционирование | Обоснование |
| --- | --- | --- | --- | --- | --- | --- | --- |
| bronze.customer | custkey bigint, mktsegment varchar | 150000 | 0.227193 | Parquet | ZSTD | нет | Проекция без бизнес-фильтров; все исходные строки. Проверка NULL/ключей/диапазонов до Silver. |
| bronze.orders | orderkey bigint, custkey bigint, orderdate date, shippriority integer | 1500000 | 6.669395 | Parquet | ZSTD | нет | Проекция без бизнес-фильтров; все исходные строки. Проверка NULL/ключей/диапазонов до Silver. |
| bronze.lineitem | orderkey bigint, extendedprice double, discount double, shipdate date | 6001215 | 38.598805 | Parquet | ZSTD | нет | Проекция без бизнес-фильтров; все исходные строки. Проверка NULL/ключей/диапазонов до Silver. |

### Silver

| Таблица | Колонки | Строк | MiB data files | Формат | Сжатие | Партиционирование | Обоснование |
| --- | --- | --- | --- | --- | --- | --- | --- |
| silver.shipping_order_lines | orderkey bigint, orderdate date, shippriority integer, shipdate date, extendedprice double, discount double, line_revenue double, mktsegment varchar | 30519 | 0.396678 | Parquet | ZSTD | нет | Нормализация сегмента перед фильтром, два JOIN, три фильтра и line_revenue без CAST/округления. |

### Gold

| Таблица | Колонки | Строк | MiB data files | Формат | Сжатие | Партиционирование | Обоснование |
| --- | --- | --- | --- | --- | --- | --- | --- |
| gold.shipping_priority | orderkey bigint, revenue double, orderdate date, shippriority integer | 10 | 0.000807 | Parquet | ZSTD | нет | Агрегация Silver по заказу и только затем top-10. |

Проверки качества охватывают NULL, уникальность ключей customer/orders, положительные идентификаторы, ссылки между таблицами, конечность цен/скидок и допустимость их диапазонов. TPC-H не содержит обнаруженных нарушений: все счётчики проверки равны нулю; удаление ошибочных строк не потребовалось. В SQL Silver upper(trim(mktsegment)) теперь вычисляется в подзапросе до фильтра BUILDING. Отдельная проверка Bronze подтверждает отсутствие изменений от нормализации, поэтому состав выборки строго совпадает с исходным Q3. Позиции заказов не удаляются и DISTINCT не применяется.

Parquet/ZSTD — базовое сочетание для колонночной аналитики; его предпочтительность проверяется экспериментом, а не принимается как результат заранее. При sf1 нет доказанной выгоды месячного партиционирования: оно добавляет мелкие файлы; Gold на десять строк партиционировать нецелесообразно. Типы и значения сохраняются; varchar теряет ограничение длины в Iceberg. Позиции lineitem не дедуплицируются.

Проверка: **passed**. Нарушения качества: `{"customer_invalid": 0, "customer_duplicate_keys": 0, "orders_invalid": 0, "segment_normalization_changes": 0, "orders_orphans": 0, "orders_duplicate_keys": 0, "lineitem_invalid": 0, "lineitem_orphans": 0}`.
Сумма line_revenue до материализации: `1115271243.5140996`, после: `1115271243.5140946`. Повторный pipeline: `passed`. Полное равенство Silver проверено двусторонним EXCEPT ALL.

Разница сумм в последних десятичных знаках возникает из-за порядка сложения DOUBLE; строки Silver совпадают точно по EXCEPT ALL. В таблице ниже revenue форматируется до четырёх знаков только для чтения; исходные значения без округления сохранены в CSV/JSON.

| orderkey | revenue | orderdate | shippriority |
| --- | --- | --- | --- |
| 2456423 | 406181.0111 | 1995-03-05 | 0 |
| 3459808 | 405838.6989 | 1995-03-04 | 0 |
| 492164 | 390324.0610 | 1995-02-19 | 0 |
| 1188320 | 384537.9359 | 1995-03-09 | 0 |
| 2435712 | 378673.0558 | 1995-02-26 | 0 |
| 4878020 | 378376.7952 | 1995-03-12 | 0 |
| 5521732 | 375153.9215 | 1995-03-13 | 0 |
| 2628192 | 373133.3094 | 1995-02-22 | 0 |
| 993600 | 371407.4595 | 1995-03-05 | 0 |
| 2300070 | 367371.1452 | 1995-03-13 | 0 |

## 5. Тесты производительности

| Сжатие на Bronze | Время запроса | Размер Bronze, МБ (10^6) | Вывод |
| --- | --- | --- | --- |
| GZIP | 0.647198 s | 47.988274 | Фактическая медиана пяти прогретых запусков |
| ZSTD | 0.557981 s | 47.736043 | Фактическая медиана пяти прогретых запусков |

Для эксперимента используются независимые физические копии трёх Bronze-таблиц в lakehouse.benchmark: основной Bronze не удаляется и не пересоздаётся бенчмарком. Копии изолируют конфигурации формата/кодека и не меняют основной ELT pipeline. Идентичность строк подтверждается двусторонним EXCEPT ALL, одинаковость типов — SHOW COLUMNS; меняются только format и compression_codec. Полный Q3 выполняется над соответствующей тройкой копий, а не над Gold.

Один warmup и пять измерений на sf1, последовательно, фиксированная конфигурация движка. Порядок сценариев в измеряемых сериях перемешивается с seed=1. Время — клиентский монотонный wall clock, включая HTTP и получение всех страниц. Время записи — отдельный CTAS каждой таблицы, проверки данных исключены. Размер — активные data files content=0 из $files, metadata и старые snapshots исключены; MiB=2^20, МБ=10^6. Query ID и сырые Trino stats сохранены. processedBytes не выдаётся за точные физические S3 bytes.

| Format | Codec | Rows | Size MiB | Write s | Query median s | Min s | Max s | Files |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| PARQUET | GZIP | 7651215 | 45.765 | 4.878 | 0.647 | 0.629 | 2.236 | 4 |
| PARQUET | ZSTD | 7651215 | 45.525 | 3.006 | 0.558 | 0.491 | 0.660 | 4 |
| ORC | ZSTD | 7651215 | 50.927 | 3.878 | 0.753 | 0.534 | 1.127 | 4 |

Parquet/ZSTD относительно Parquet/GZIP: экономия места 0.526%, изменение времени чтения -13.785%, записи -38.390%. Положительное изменение времени означает замедление.

Минимальная медиана чтения: PARQUET/ZSTD; минимальный размер: PARQUET/ZSTD. В этой серии Parquet/ZSTD также дал меньшее суммарное время записи, чем остальные сценарии; результат относится только к измеренной нагрузке и среде.

Ограничения: локальная машина и прогретые кеши, без гарантии cold-cache, прямых CPU cycles и повторной серии записей. На latency влияют CPU, IO, планирование и фоновые процессы. Результаты не являются официальным TPC-H benchmark.

## 6. Часть 2

### 6.1. Понять и объяснить

1. Большие данные требуют масштабирования хранения и вычислений независимо. Lakehouse сочетает объектное хранение и табличные метаданные для нескольких движков; обычная БД удобнее для малых транзакционных нагрузок. sf1 служит учебной проверкой архитектуры, а не доказательством преимуществ на огромном объёме.
2. В демонстрационной копии Silver ADD COLUMN и RENAME COLUMN меняют metadata с column IDs. Старые файлы должны сохраниться, чтение добавленной колонки для прежних строк возвращает NULL.
3. Iceberg snapshots описывают состояние data files. Time travel читает выбранный snapshot без изменения текущего состояния; rollback делает предыдущее состояние текущим. Это не общий механизм отката всех schema changes.

Практика подтверждена: 100 строк после evolution, 0 non-NULL в новой колонке; data-file paths/размеры и checksum совпали до/после. Snapshot 7309313712021183814 → 3561732071680956645; строк до 10, после удаления 9, в историческом чтении 10, после rollback 10. Полные строки после восстановления совпали.

### 6.2. Подключить инструмент

Выбран Superset для воспроизводимой проверки BI через SQL Lab. Dockerfile устанавливает Trino SQLAlchemy driver; init выполняет migrations и регистрирует подключение Lakehouse Trino с URI `trino://superset@trino:8080/lakehouse/bronze`. Команды: `make up`, `make bi`. Проверка использует login/CSRF и `/api/v1/sqllab/execute/`, читает Bronze и Gold, сопоставляет строки с Trino; access tokens в evidence не сохраняются.

```sql
SELECT mktsegment, count(*) AS customers
FROM lakehouse.bronze.customer
GROUP BY mktsegment ORDER BY customers DESC;
```

Статус SQL Lab: **passed**. Источники доказательств: results/bi.json, evidence/README.md; реальные UI-скриншоты: [Bronze](evidence/superset-bronze.jpg), [Gold](evidence/superset-gold.jpg).

График Gold создан и воспроизводимо импортируется командой make bi из docker/superset/q3-chart.zip: [реальный скриншот](evidence/superset-gold-chart.jpg). Используется MAX(revenue) по orderkey и сортировка по убыванию.

Фактические статусы: validation: пройден, benchmark: пройден, Iceberg: пройден, BI: пройден, smoke: пройден.

## 7. Выводы

Физические слои Bronze/Silver/Gold разделили сохранение исходных проекций, фильтрацию/обогащение и бизнес-агрегацию Q3. Сопоставление с source, EXCEPT ALL и повторная перестройка подтвердили сохранение данных и совпадение Gold с эталоном. Parquet/ZSTD изменил объём на -0.526% относительно GZIP; наименьшая медиана Q3 получена у PARQUET/ZSTD, что делает это сочетание предпочтительным именно по времени чтения в данном эксперименте. Schema evolution сохранила старые data files, а snapshots позволили прочитать и восстановить состояние после удаления; Superset подтвердил доступ к Bronze через общий Lakehouse.

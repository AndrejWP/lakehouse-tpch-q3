# Доказательства выполнения

Машиночитаемые SQL, query IDs, stats, таблицы результатов и snapshot IDs находятся в `../results/` и относятся к реальным запускам. `environment.json` фиксирует среду без конфигурации с паролями. `compose-status.json` — снимок сервисов. Логи не включаются, поскольку могут содержать секреты из сторонних библиотек.

Для скриншотов преподавателю:

1. `docker compose ps`: postgres, minio, lakekeeper, trino, superset healthy.
2. MinIO console: bucket lakehouse, папки warehouse и реальные Parquet/ORC files.
3. Trino: SELECT из Gold с ORDER BY revenue DESC и `$files` Bronze.
4. Superset SQL Lab: выбран Lakehouse Trino, SQL к lakehouse.bronze.customer, результат по сегментам.
5. Superset SQL Lab: топ-10 из lakehouse.gold.shipping_priority (при желании Bar chart).
6. JSON schema evolution: одинаковые файлы до/после; NULL в новой колонке.
7. JSON snapshot: реальные IDs, числа до удаления/после/после rollback.

Скриншоты добавляются только после реального выполнения. Не включайте в кадр `.env` и формы с credentials. Их отсутствие не заменяется фиктивными изображениями.

Сохранённые реальные скриншоты: [Superset Bronze](superset-bronze.jpg), [Superset Gold](superset-gold.jpg).

[Столбчатый график Gold](superset-gold-chart.jpg) сохранён в локальном Superset; переносимая конфигурация — `../docker/superset/q3-chart.zip`, автоматический импорт выполняет `make bi`.

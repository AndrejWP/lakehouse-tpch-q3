# Результаты

Артефакты создаются соответствующими исполняемыми этапами, не заранее:

| Файл | Команда |
|---|---|
| bootstrap.json | make bootstrap |
| pipeline.json | make pipeline |
| validation.json, q3_result.csv | make validate-rerun |
| benchmark.csv/json/md | make benchmark |
| metrics.json | make metrics |
| iceberg_demo.json | make iceberg |
| bi.json | make bi |
| smoke.json | make smoke |
| static_checks.json | make static PYTHON=.venv/bin/python |

`run_id` связывает результаты с конкретной перестройкой sf1. `status=failed` — ошибка, `not_run` — этап не запускался, отсутствие файла не считается успешным результатом. Время клиента измеряется монотонными часами; точные детали в README.

Финальный аудит: `make audit-runtime` проверяет исходные измерения и текущие физические копии без их пересоздания; `final_audit.json` содержит хеши benchmark-файлов. В `history/iceberg_demo.initial.json` сохранена предыдущая демонстрация Iceberg до повторной проверки. Времена исходного бенчмарка не перезаписываются аудитом.

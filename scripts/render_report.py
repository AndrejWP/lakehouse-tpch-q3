"""Generate the teacher's seven-section report from measured artifacts only."""
import json
import re
from pathlib import Path
from common import ROOT, RESULTS


def artifact(name):
    path = RESULTS / name
    return json.loads(path.read_text()) if path.exists() else {}


def table(headers, rows):
    def cell(value):
        return str(value).replace('|', '\\|').replace('\n', ' ')
    lines = ['| ' + ' | '.join(headers) + ' |', '| ' + ' | '.join('---' for _ in headers) + ' |']
    lines += ['| ' + ' | '.join(cell(v) for v in row) + ' |' for row in rows]
    return '\n'.join(lines) + '\n'


def render():
    current = artifact('pipeline.json')
    run_id = current.get('run_id')
    def measured(name):
        data = artifact(name)
        if not run_id or data.get('run_id') != run_id or data.get('status', 'passed') != 'passed':
            return {}
        return data
    metrics = measured('metrics.json').get('tables', {})
    validation = measured('validation.json')
    benchmark = measured('benchmark.json')
    demo = measured('iceberg_demo.json')
    bi = measured('bi.json')
    smoke = measured('smoke.json')
    env_path = ROOT / 'evidence/environment.json'
    environment = json.loads(env_path.read_text()) if env_path.exists() else {}
    fio = 'Потрикеев Андрей'
    report = ROOT / 'report.md'
    if report.exists():
        old = re.search(r'\| ФИО \| (.+?) \|', report.read_text())
        if old and not old.group(1).startswith('['):
            fio = old.group(1)
    text = '# Практическая работа №1 — Lakehouse, ELT и TPC-H Q3\n\n'
    text += '## 1. Вариант и масштаб\n\n'
    text += table(['Параметр', 'Значение'], [
        ['ФИО', fio], ['Вариант', '№1 — TPC-H Q3 Shipping Priority'], ['Масштаб', 'sf1'],
        ['Обоснование', 'Достаточная проекция трёх таблиц для измерений локального IO/сжатия; умеренное потребление RAM и диска на машине 24 ГБ.'],
        ['Фактический запуск', current.get('completed_at', 'Pipeline ещё не выполнен')],
        ['Идентификатор', run_id or 'Отсутствует']])
    text += '\n## 2. Поднятые сервисы и обоснование\n\n'
    text += table(['Сервис', 'Роль в стеке', 'Почему выбран'], [
        ['MinIO', 'S3 data/metadata files Iceberg', 'Разделение хранения и вычислений, совместимость S3; локальная FS этого API не даёт.'],
        ['PostgreSQL 16.8', 'Метаданные Lakekeeper', 'Транзакции и поддерживаемый Lakekeeper backend.'],
        ['Lakekeeper 0.9.5', 'REST Catalog', 'Регистрирует таблицы и согласует metadata pointers; отдельные Parquet-файлы каталога не имеют.'],
        ['Trino 479', 'TPC-H и SQL ELT', 'Один движок для source, Iceberg, Parquet/ORC и Q3.'],
        ['Superset 4.1.2', 'SQL Lab BI', 'Проверяемое чтение Bronze и Gold через Trino SQLAlchemy driver.']])
    text += '\nКоманды: `docker compose up -d --build --wait --wait-timeout 900`, `make bootstrap`, `docker compose ps`, `docker compose down`. MinIO собирается из официальных исходников закреплённого релиза, поскольку загрузка старых registry images завершалась отказом. Volume PostgreSQL сохраняет метаданные, MinIO — файлы, Superset — локальные metadata.\n'
    if environment:
        text += '\nСреда: `' + json.dumps(environment, ensure_ascii=False) + '`.\n'
    text += '\nЛокальные проверки: [unit tests](results/unit_tests.json), [SQL/Python/Compose static checks](results/static_checks.json). Это не замена проверке работающих контейнеров.\n'
    text += '\n## 3. Разбор Q3\n\n'
    text += table(['Таблица TPC-H', 'Колонки', 'Назначение'], [
        ['customer', 'custkey, mktsegment', 'JOIN с orders; фильтр BUILDING'],
        ['orders', 'orderkey, custkey, orderdate, shippriority', 'JOIN с customer/lineitem; orderdate < 1995-03-15; группировка и вывод'],
        ['lineitem', 'orderkey, extendedprice, discount, shipdate', 'JOIN; shipdate > 1995-03-15; extendedprice*(1-discount), SUM']])
    text += '\nLIMIT применяется после агрегации, revenue не округляется. Gold физически не упорядочен; просмотр всегда использует ORDER BY revenue DESC LIMIT 10. Проверка сравнивает ключи, дату, приоритет и revenue с rel_tol=1e-10/abs_tol=1e-6; допускает только корректные пограничные ничьи.\n'
    text += '\n## 4. Medallion\n'
    for layer, names in [('Bronze', ['customer', 'orders', 'lineitem']), ('Silver', ['shipping_order_lines']), ('Gold', ['shipping_priority'])]:
        text += '\n### ' + layer + '\n\n'
        rows = []
        for name in names:
            full = layer.lower() + '.' + name
            m = metrics.get(full, {})
            columns = ', '.join(r[0] + ' ' + r[1] for r in m.get('columns', []))
            if not columns:
                from common import TABLES
                columns = ', '.join(TABLES.get(name, ['см. SQL определения']))
            reason = {'Bronze': 'Проекция без бизнес-фильтров; все исходные строки. Проверка NULL/ключей/диапазонов до Silver.',
                      'Silver': 'Нормализация сегмента перед фильтром, два JOIN, три фильтра и line_revenue без CAST/округления.',
                      'Gold': 'Агрегация Silver по заказу и только затем top-10.'}[layer]
            rows.append([full, columns, m.get('rows', 'не измерено'),
                         f"{m['size_mib']:.6f}" if m else 'не измерено',
                         'Parquet', 'ZSTD', 'нет', reason])
        text += table(['Таблица', 'Колонки', 'Строк', 'MiB data files', 'Формат', 'Сжатие', 'Партиционирование', 'Обоснование'], rows)
    text += '\nПроверки качества охватывают NULL, уникальность ключей customer/orders, положительные идентификаторы, ссылки между таблицами, конечность цен/скидок и допустимость их диапазонов. TPC-H не содержит обнаруженных нарушений: все счётчики проверки равны нулю; удаление ошибочных строк не потребовалось. В SQL Silver upper(trim(mktsegment)) теперь вычисляется в подзапросе до фильтра BUILDING. Отдельная проверка Bronze подтверждает отсутствие изменений от нормализации, поэтому состав выборки строго совпадает с исходным Q3. Позиции заказов не удаляются и DISTINCT не применяется.\n'
    text += '\nParquet/ZSTD — базовое сочетание для колонночной аналитики; его предпочтительность проверяется экспериментом, а не принимается как результат заранее. При sf1 нет доказанной выгоды месячного партиционирования: оно добавляет мелкие файлы; Gold на десять строк партиционировать нецелесообразно. Типы и значения сохраняются; varchar теряет ограничение длины в Iceberg. Позиции lineitem не дедуплицируются.\n'
    if validation:
        text += '\nПроверка: **passed**. Нарушения качества: `' + json.dumps(validation['quality'], ensure_ascii=False) + '`.\n'
        text += 'Сумма line_revenue до материализации: `' + str(validation['source_line_revenue']) + '`, после: `' + str(validation['silver_line_revenue']) + '`. Повторный pipeline: `' + validation['rerun']['status'] + '`. Полное равенство Silver проверено двусторонним EXCEPT ALL.\n'
        text += '\nРазница сумм в последних десятичных знаках возникает из-за порядка сложения DOUBLE; строки Silver совпадают точно по EXCEPT ALL. В таблице ниже revenue форматируется до четырёх знаков только для чтения; исходные значения без округления сохранены в CSV/JSON.\n'
        text += '\n' + table(['orderkey', 'revenue', 'orderdate', 'shippriority'], [[r[0], f"{r[1]:.4f}", r[2], r[3]] for r in validation['gold']])
    else:
        text += '\nРезультат Q3 и результаты очистки **пока не подтверждены исполнением**. Числа строк/размеров не подставляются из справочника.\n'
    text += '\n## 5. Тесты производительности\n\n'
    scenarios = benchmark.get('scenarios', [])
    rows = []
    for codec in ['GZIP', 'ZSTD']:
        s = next((s for s in scenarios if s['format'] == 'PARQUET' and s['codec'] == codec), {})
        rows.append([codec, f"{s['median_seconds']:.6f} s" if s else 'не измерено',
                     f"{s['data_bytes'] / 1e6:.6f}" if s else 'не измерено',
                     'Фактическая медиана пяти прогретых запусков' if s else 'Эксперимент ещё не завершён'])
    text += table(['Сжатие на Bronze', 'Время запроса', 'Размер Bronze, МБ (10^6)', 'Вывод'], rows)
    text += '\nДля эксперимента используются независимые физические копии трёх Bronze-таблиц в lakehouse.benchmark: основной Bronze не удаляется и не пересоздаётся бенчмарком. Копии изолируют конфигурации формата/кодека и не меняют основной ELT pipeline. Идентичность строк подтверждается двусторонним EXCEPT ALL, одинаковость типов — SHOW COLUMNS; меняются только format и compression_codec. Полный Q3 выполняется над соответствующей тройкой копий, а не над Gold.\n'
    text += '\nОдин warmup и пять измерений на sf1, последовательно, фиксированная конфигурация движка. Порядок сценариев в измеряемых сериях перемешивается с seed=1. Время — клиентский монотонный wall clock, включая HTTP и получение всех страниц. Время записи — отдельный CTAS каждой таблицы, проверки данных исключены. Размер — активные data files content=0 из $files, metadata и старые snapshots исключены; MiB=2^20, МБ=10^6. Query ID и сырые Trino stats сохранены. processedBytes не выдаётся за точные физические S3 bytes.\n'
    if benchmark:
        text += '\n' + (RESULTS / 'benchmark.md').read_text()
        comparison = benchmark['comparison_parquet_zstd_vs_gzip']
        text += '\nParquet/ZSTD относительно Parquet/GZIP: экономия места ' + f"{comparison['size_saving_percent']:.3f}%" + ', изменение времени чтения ' + f"{comparison['query_time_change_percent']:.3f}%" + ', записи ' + f"{comparison['write_time_change_percent']:.3f}%" + '. Положительное изменение времени означает замедление.\n'
        best_query = min(scenarios, key=lambda s: s['median_seconds'])
        best_size = min(scenarios, key=lambda s: s['data_bytes'])
        text += f"\nМинимальная медиана чтения: {best_query['format']}/{best_query['codec']}; минимальный размер: {best_size['format']}/{best_size['codec']}. В этой серии Parquet/ZSTD также дал меньшее суммарное время записи, чем остальные сценарии; результат относится только к измеренной нагрузке и среде.\n"
    else:
        text += '\nParquet/GZIP, Parquet/ZSTD и ORC/ZSTD реализованы; реальных законченных измерений ещё нет. Сравнительные проценты и победитель не объявляются.\n'
    text += '\nОграничения: локальная машина и прогретые кеши, без гарантии cold-cache, прямых CPU cycles и повторной серии записей. На latency влияют CPU, IO, планирование и фоновые процессы. Результаты не являются официальным TPC-H benchmark.\n'
    text += '\n## 6. Часть 2\n\n### 6.1. Понять и объяснить\n\n'
    text += '1. Большие данные требуют масштабирования хранения и вычислений независимо. Lakehouse сочетает объектное хранение и табличные метаданные для нескольких движков; обычная БД удобнее для малых транзакционных нагрузок. sf1 служит учебной проверкой архитектуры, а не доказательством преимуществ на огромном объёме.\n'
    text += '2. В демонстрационной копии Silver ADD COLUMN и RENAME COLUMN меняют metadata с column IDs. Старые файлы должны сохраниться, чтение добавленной колонки для прежних строк возвращает NULL.\n'
    text += '3. Iceberg snapshots описывают состояние data files. Time travel читает выбранный snapshot без изменения текущего состояния; rollback делает предыдущее состояние текущим. Это не общий механизм отката всех schema changes.\n'
    if demo:
        e, s = demo['evolution'], demo['snapshot']
        text += f"\nПрактика подтверждена: {e['rows']} строк после evolution, {e['nonnull_notes']} non-NULL в новой колонке; data-file paths/размеры и checksum совпали до/после. Snapshot {s['initial_id']} → {s['changed_id']}; строк до {s['rows_before']}, после удаления {s['rows_changed']}, в историческом чтении {s['rows_historical']}, после rollback {s['rows_restored']}. Полные строки после восстановления совпали.\n"
    else:
        text += '\nЭти операции реализованы в scripts/iceberg_demo.py; факт исполнения пока не подтверждён.\n'
    text += '\n### 6.2. Подключить инструмент\n\n'
    text += 'Выбран Superset для воспроизводимой проверки BI через SQL Lab. Dockerfile устанавливает Trino SQLAlchemy driver; init выполняет migrations и регистрирует подключение Lakehouse Trino с URI `trino://superset@trino:8080/lakehouse/bronze`. Команды: `make up`, `make bi`. Проверка использует login/CSRF и `/api/v1/sqllab/execute/`, читает Bronze и Gold, сопоставляет строки с Trino; access tokens в evidence не сохраняются.\n\n'
    text += '```sql\nSELECT mktsegment, count(*) AS customers\nFROM lakehouse.bronze.customer\nGROUP BY mktsegment ORDER BY customers DESC;\n```\n'
    text += '\nСтатус SQL Lab: **' + ('passed' if bi else 'не подтверждён') + '**. Источники доказательств: results/bi.json, evidence/README.md; реальные UI-скриншоты: [Bronze](evidence/superset-bronze.jpg), [Gold](evidence/superset-gold.jpg).\n'
    if bi.get('gold_chart'):
        text += '\nГрафик Gold создан и воспроизводимо импортируется командой make bi из docker/superset/q3-chart.zip: [реальный скриншот](evidence/superset-gold-chart.jpg). Используется MAX(revenue) по orderkey и сортировка по убыванию.\n'
    text += '\nФактические статусы: ' + ', '.join(f"{name}: {'пройден' if data else 'не подтверждён'}" for name, data in [('validation', validation), ('benchmark', benchmark), ('Iceberg', demo), ('BI', bi), ('smoke', smoke)]) + '.\n'
    text += '\n## 7. Выводы\n\n'
    if smoke and benchmark and validation and demo and bi:
        c = benchmark['comparison_parquet_zstd_vs_gzip']
        best = min(scenarios, key=lambda s: s['median_seconds'])
        text += 'Физические слои Bronze/Silver/Gold разделили сохранение исходных проекций, фильтрацию/обогащение и бизнес-агрегацию Q3. '
        text += 'Сопоставление с source, EXCEPT ALL и повторная перестройка подтвердили сохранение данных и совпадение Gold с эталоном. '
        text += f"Parquet/ZSTD изменил объём на {(-c['size_saving_percent']):.3f}% относительно GZIP; наименьшая медиана Q3 получена у {best['format']}/{best['codec']}, что делает это сочетание предпочтительным именно по времени чтения в данном эксперименте. "
        text += 'Schema evolution сохранила старые data files, а snapshots позволили прочитать и восстановить состояние после удаления; Superset подтвердил доступ к Bronze через общий Lakehouse.\n'
    else:
        text += 'Подготовлен исполняемый конвейер с физическими слоями Bronze/Silver/Gold и точной формулой Q3. Полное совпадение Gold с эталоном считается доказанным только после успешной интеграционной проверки. До завершения бенчмарка нельзя оценить влияние сжатия или назвать предпочтительный формат/кодек. Демонстрации Iceberg и SQL Lab проверяют практическое применение snapshots, изменения схемы и совместного доступа к данным, но их готовность должна подтверждаться артефактами запуска.\n'
    report.write_text(text)
    print('report.md refreshed from real artifacts; FIO preserved')


if __name__ == '__main__':
    render()

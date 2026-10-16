SHELL := /bin/sh
PYTHON ?= python3
DC := docker compose
RUN := $(DC) run --rm --no-deps runner python
.NOTPARALLEL:
.PHONY: env up bootstrap pipeline validate validate-rerun benchmark metrics iceberg bi report all smoke test static logs status down audit audit-runtime package

env:
	$(PYTHON) scripts/env.py
up: env
	$(DC) up -d --build --wait --wait-timeout 900
	$(PYTHON) scripts/environment.py
bootstrap:
	sh scripts/bootstrap.sh
pipeline:
	$(RUN) scripts/run_pipeline.py
validate:
	$(RUN) scripts/validate.py
validate-rerun:
	$(RUN) scripts/validate.py --rerun
benchmark:
	$(RUN) scripts/benchmark.py
metrics:
	$(RUN) scripts/collect_metrics.py
iceberg:
	$(RUN) scripts/iceberg_demo.py
bi:
	$(RUN) scripts/check_bi.py
report:
	$(PYTHON) scripts/render_report.py
all:
	$(MAKE) up
	$(MAKE) bootstrap
	$(MAKE) pipeline
	$(MAKE) validate-rerun
	$(MAKE) iceberg
	$(MAKE) benchmark
	$(MAKE) metrics
	$(MAKE) bi
	$(MAKE) smoke
	$(MAKE) report
smoke:
	sh scripts/smoke.sh
test:
	$(PYTHON) -m unittest discover -s tests -v
static:
	$(PYTHON) scripts/static_check.py
logs:
	$(DC) logs --tail=100
status:
	$(DC) ps -a
down:
	$(DC) down

audit:
	$(PYTHON) scripts/audit.py
audit-runtime:
	TRINO_URL=http://localhost:8080 $(PYTHON) scripts/audit.py --runtime
package:
	$(PYTHON) scripts/package.py

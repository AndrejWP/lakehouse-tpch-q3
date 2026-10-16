#!/bin/sh
set -eu
superset db upgrade
superset init
python /app/pythonpath/register.py

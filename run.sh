#!/bin/bash
cd /opt/tg-controller
set -a
source .env
set +a
exec python3 main.py

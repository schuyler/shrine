#!/bin/sh
rsync -avz \
    --exclude='.venv/' \
    --exclude='__pycache__/' \
    --exclude='*.pyc' \
    --exclude='.pio/' \
    --exclude='.DS_Store' \
    --exclude='.envrc' \
    --exclude='nvs/*.csv' \
    --exclude='wled/*.bin' \
    --exclude='pd/' \
    ./ corazon.local:shrine/

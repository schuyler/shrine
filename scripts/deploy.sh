#!/bin/sh
rsync -avz \
    --exclude='.venv/' \
    --exclude='__pycache__/' \
    --exclude='*.pyc' \
    --exclude='.pio/' \
    --exclude='.DS_Store' \
    ./ corazon:shrine/

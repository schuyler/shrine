#!/bin/sh
set -e

rsync -avz \
    --exclude='.venv/' \
    --exclude='__pycache__/' \
    --exclude='*.pyc' \
    --exclude='.pio/' \
    --exclude='.DS_Store' \
    --exclude='.envrc' \
    --exclude='nvs/*.csv' \
    --exclude='wled/*.bin' \
    --exclude='pd/main.pd' \
    ./ corazon.local:shrine/

echo
echo "Restarting shrine services..."
ssh corazon.local sudo systemctl restart shrine-pd shrine-conductor shrine-leds
echo "Done."

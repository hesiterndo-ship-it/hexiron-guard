#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$BASE_DIR"

DB_PATH_VALUE="${DB_PATH:-$BASE_DIR/guardbot.db}"
BACKUP_DIR_VALUE="${BACKUP_DIR:-$BASE_DIR/backups}"
mkdir -p "$BACKUP_DIR_VALUE"

STAMP="$(date +%Y%m%d_%H%M%S)"
OUT="$BACKUP_DIR_VALUE/guardbot_${STAMP}.db"

if command -v sqlite3 >/dev/null 2>&1; then
  sqlite3 "$DB_PATH_VALUE" ".backup '$OUT'"
else
  python - "$DB_PATH_VALUE" "$OUT" <<'PY'
import sqlite3
import sys
src, dst = sys.argv[1], sys.argv[2]
with sqlite3.connect(src) as a, sqlite3.connect(dst) as b:
    a.backup(b)
PY
fi

printf 'Backup created: %s\n' "$OUT"

#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$BASE_DIR"

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 /path/to/backup.db" >&2
  exit 2
fi

SOURCE="$1"
DB_PATH_VALUE="${DB_PATH:-$BASE_DIR/guardbot.db}"

if [[ ! -f "$SOURCE" ]]; then
  echo "Backup not found: $SOURCE" >&2
  exit 1
fi

mkdir -p "$(dirname "$DB_PATH_VALUE")"

if [[ -f "$DB_PATH_VALUE" ]]; then
  cp "$DB_PATH_VALUE" "${DB_PATH_VALUE}.before_restore_$(date +%Y%m%d_%H%M%S)"
fi

python - "$SOURCE" "$DB_PATH_VALUE" <<'PY'
import sqlite3
import sys
src, dst = sys.argv[1], sys.argv[2]
with sqlite3.connect(src) as a, sqlite3.connect(dst) as b:
    a.backup(b)
PY

printf 'Database restored to: %s\n' "$DB_PATH_VALUE"

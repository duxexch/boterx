#!/bin/bash
# post-merge.sh — يعمل تلقائياً بعد كل merge لمهام Task Agents
# آمن للتكرار (idempotent) — لا يطلب أي إدخال تفاعلي
set -e

echo "=== Boterx post-merge setup ==="

# تشغيل migrate.py إن وُجد (CSV → SQLite، آمن للتكرار)
if [ -f "migrate.py" ]; then
  echo "→ running migrate.py..."
  # --quiet تجاهل إن لم يدعمه migrate.py
  python3 migrate.py 2>&1 || true
fi

echo "=== post-merge done ==="

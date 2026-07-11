#!/data/data/com.termux/files/usr/bin/bash
# run_migration.sh
# Использование:
#   export DATABASE_URL="postgresql://postgres.xxxx:PASSWORD@aws-1-...:6543/postgres"
#   bash run_migration.sh

set -e

if [ -z "$DATABASE_URL" ]; then
  echo "Заполни DATABASE_URL (та же pooler-строка с aws-1- и портом 6543, что у vector-chat-api на Render)."
  exit 1
fi

# psql в Termux ставится через pkg, а не pip
if ! command -v psql >/dev/null 2>&1; then
  echo "Устанавливаю postgresql-client..."
  pkg install -y postgresql
fi

MIGRATION_FILE="unlock_requests_migration.sql"

if [ ! -f "$MIGRATION_FILE" ]; then
  echo "Файл $MIGRATION_FILE не найден рядом со скриптом. Скачай его из чата и положи в эту же папку."
  exit 1
fi

echo "Применяю миграцию к базе..."
psql "$DATABASE_URL" -f "$MIGRATION_FILE"

echo ""
echo "Проверка, что таблицы появились:"
psql "$DATABASE_URL" -c "\dt public.unlock_requests"
psql "$DATABASE_URL" -c "\dt public.device_accounts"

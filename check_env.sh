#!/data/data/com.termux/files/usr/bin/bash
# check_env.sh
# Использование:
#   export RENDER_API_KEY="rnd_xxxxxxxxxxxx"      # Render Dashboard -> Account Settings -> API Keys
#   export BOT_SERVICE_ID="srv-xxxxxxxx"          # из URL сервиса бота на Render
#   export BLIZKO_SERVICE_ID="srv-yyyyyyyy"       # из URL сервиса vector-chat-api на Render
#   bash check_env.sh

set -e

if [ -z "$RENDER_API_KEY" ] || [ -z "$BOT_SERVICE_ID" ] || [ -z "$BLIZKO_SERVICE_ID" ]; then
  echo "Заполни переменные RENDER_API_KEY, BOT_SERVICE_ID, BLIZKO_SERVICE_ID перед запуском (см. комментарии в скрипте)."
  exit 1
fi

get_env() {
  local service_id="$1"
  curl -s -H "Authorization: Bearer $RENDER_API_KEY" \
    "https://api.render.com/v1/services/$service_id/env-vars"
}

echo "=== Переменные бота (@Rezumeizi_bot) ==="
BOT_ENV=$(get_env "$BOT_SERVICE_ID")
echo "$BOT_ENV" | grep -A1 '"key": "BLIZKO_API_KEY"' || echo "BLIZKO_API_KEY не найден"
echo "$BOT_ENV" | grep -A1 '"key": "BLIZKO_API_URL"' || echo "BLIZKO_API_URL не найден"

echo ""
echo "=== Переменные vector-chat-api ==="
BLIZKO_ENV=$(get_env "$BLIZKO_SERVICE_ID")
echo "$BLIZKO_ENV" | grep -A1 '"key": "INTERNAL_API_KEY"' || echo "INTERNAL_API_KEY не найден"
echo "$BLIZKO_ENV" | grep -A1 '"key": "SUPABASE_URL"' || echo "SUPABASE_URL не найден"
echo "$BLIZKO_ENV" | grep -A1 '"key": "SUPABASE_SERVICE_KEY"' || echo "SUPABASE_SERVICE_KEY не найден"
echo "$BLIZKO_ENV" | grep -A1 '"key": "RESUME_BOT_URL"' || echo "RESUME_BOT_URL не найден"

echo ""
echo "⚠️  Значения (value) Render не показывает в списке напрямую если помечены как secret —"
echo "    сравни BLIZKO_API_KEY и INTERNAL_API_KEY вручную открыв каждую переменную на Render,"
echo "    либо запроси значения так:"
echo ""
echo "    curl -s -H \"Authorization: Bearer \$RENDER_API_KEY\" \\"
echo "      https://api.render.com/v1/services/\$BOT_SERVICE_ID/env-vars | grep -A2 BLIZKO_API_KEY"

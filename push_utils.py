# push_utils.py
# Положи этот файл рядом с main.py в репозитории vector-chat-api.
#
# Отвечает за:
# 1. Поиск push-подписок пользователя в Supabase (через service_role ключ, минуя RLS)
# 2. Отправку push через pywebpush
# 3. Удаление "мёртвых" подписок (когда браузер отписался / устройство недоступно)

import os
import json
import httpx
from pywebpush import webpush, WebPushException

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY", "")
VAPID_CLAIM_EMAIL = os.environ.get("VAPID_CLAIM_EMAIL", "mailto:admin@example.com")


def _supabase_headers():
    return {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": "Bearer " + SUPABASE_SERVICE_KEY,
        "Content-Type": "application/json"
    }


async def get_subscriptions_for_user(user_id: str):
    """Достаёт все push-подписки конкретного пользователя из Supabase."""
    url = SUPABASE_URL + "/rest/v1/push_subscriptions?user_id=eq." + user_id + "&select=id,endpoint,p256dh,auth"
    async with httpx.AsyncClient() as client:
        r = await client.get(url, headers=_supabase_headers())
        if r.status_code != 200:
            print("Ошибка получения подписок из Supabase:", r.status_code, r.text)
            return []
        return r.json()


async def delete_subscription(sub_id: str):
    """Удаляет недействительную подписку (устройство больше не существует)."""
    url = SUPABASE_URL + "/rest/v1/push_subscriptions?id=eq." + sub_id
    async with httpx.AsyncClient() as client:
        await client.delete(url, headers=_supabase_headers())


async def send_push_to_user(user_id: str, payload: dict):
    """
    Отправляет push-уведомление всем устройствам пользователя.
    payload пример:
    {
      "title": "Входящий звонок",
      "body": "Анна звонит вам",
      "type": "call",
      "callId": "abc123",
      "fromUserId": "uuid-звонящего",
      "url": "/call.html?call=abc123"
    }
    """
    subs = await get_subscriptions_for_user(user_id)
    if not subs:
        return {"sent": 0, "reason": "no_subscriptions"}

    sent = 0
    for sub in subs:
        subscription_info = {
            "endpoint": sub["endpoint"],
            "keys": {
                "p256dh": sub["p256dh"],
                "auth": sub["auth"]
            }
        }
        try:
            webpush(
                subscription_info=subscription_info,
                data=json.dumps(payload),
                vapid_private_key=VAPID_PRIVATE_KEY,
                vapid_claims={"sub": VAPID_CLAIM_EMAIL}
            )
            sent += 1
        except WebPushException as ex:
            print("Push не доставлен:", ex)
            # 404/410 — подписка больше не существует (юзер отписался / переустановил браузер)
            if ex.response is not None and ex.response.status_code in (404, 410):
                await delete_subscription(sub["id"])

    return {"sent": sent, "total": len(subs)}

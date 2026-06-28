# unlock_utils.py
# Положи рядом с main.py и push_utils.py в репозитории vector-chat-api.

import os
import secrets
import string
import httpx
from datetime import datetime, timezone

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

# Адрес бота resume-bot — там хранятся актуальные цены (админ меняет их в боте)
RESUME_BOT_URL = os.environ.get("RESUME_BOT_URL", "").rstrip("/")

# Цены по умолчанию (если бот недоступен)
DEFAULT_PRICE_UNLOCK = 199
DEFAULT_PRICE_EXTRA_BASE = 200

# Username твоего бота для оплаты — ЗАМЕНИ на актуальный
BOT_USERNAME = "your_payment_bot"


async def get_blizko_prices():
    """Берёт актуальные цены из админки бота resume-bot. При ошибке — дефолтные."""
    if not RESUME_BOT_URL:
        return {"unlock_price": DEFAULT_PRICE_UNLOCK, "extra_base_price": DEFAULT_PRICE_EXTRA_BASE}
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(RESUME_BOT_URL + "/api/blizko-prices", timeout=10.0)
            if r.status_code == 200:
                data = r.json()
                return {
                    "unlock_price": int(data.get("unlock_price", DEFAULT_PRICE_UNLOCK)),
                    "extra_base_price": int(data.get("extra_base_price", DEFAULT_PRICE_EXTRA_BASE))
                }
    except Exception as e:
        print("Не удалось получить цены от resume-bot:", e)
    return {"unlock_price": DEFAULT_PRICE_UNLOCK, "extra_base_price": DEFAULT_PRICE_EXTRA_BASE}


async def count_device_accounts(device_id: str):
    """Сколько аккаунтов уже привязано к этому устройству."""
    url = SUPABASE_URL + "/rest/v1/device_accounts?device_id=eq." + device_id + "&select=id"
    async with httpx.AsyncClient() as client:
        r = await client.get(url, headers=_headers())
        if r.status_code != 200:
            return 0
        return len(r.json())


def _headers():
    return {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": "Bearer " + SUPABASE_SERVICE_KEY,
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }


def _gen_code(length=8):
    alphabet = string.ascii_uppercase + string.digits
    # Убираем легко путаемые символы
    alphabet = alphabet.replace("0", "").replace("O", "").replace("1", "").replace("I", "")
    return "".join(secrets.choice(alphabet) for _ in range(length))


async def find_user_id_by_email(email: str):
    url = SUPABASE_URL + "/auth/v1/admin/users?email=" + email
    async with httpx.AsyncClient() as client:
        r = await client.get(url, headers=_headers())
        if r.status_code != 200:
            return None
        data = r.json()
        users = data.get("users", data if isinstance(data, list) else [])
        if not users:
            return None
        return users[0]["id"]


async def create_unlock_request(req_type: str, device_id: str, target_user_id: str | None):
    """Создаёт заявку и возвращает (request_id, telegram_deep_link, price)."""
    prices = await get_blizko_prices()

    if req_type == "unlock":
        price = prices["unlock_price"]
    else:
        existing_count = await count_device_accounts(device_id)
        # 1-й доп.аккаунт — базовая цена, 2-й — ×2, 3-й — ×4 и т.д.
        price = prices["extra_base_price"] * (2 ** existing_count)

    payload = {
        "type": req_type,
        "device_id": device_id,
        "target_user_id": target_user_id,
        "status": "pending",
        "price": price
    }

    url = SUPABASE_URL + "/rest/v1/unlock_requests"
    async with httpx.AsyncClient() as client:
        r = await client.post(url, headers=_headers(), json=payload)
        if r.status_code not in (200, 201):
            raise Exception("Supabase insert error: " + r.text)
        row = r.json()[0]

    request_id = row["id"]
    deep_link = "https://t.me/" + BOT_USERNAME + "?start=ur_" + request_id
    return request_id, deep_link, price


async def get_unlock_request(request_id: str):
    url = SUPABASE_URL + "/rest/v1/unlock_requests?id=eq." + request_id + "&select=*"
    async with httpx.AsyncClient() as client:
        r = await client.get(url, headers=_headers())
        if r.status_code != 200:
            return None
        rows = r.json()
        return rows[0] if rows else None


async def mark_request_paid(request_id: str):
    """Бот вызывает это (через /api/unlock/mark-paid) после успешной оплаты.
    Генерирует код, сохраняет его в заявке, возвращает код (бот отправляет его пользователю)."""
    req = await get_unlock_request(request_id)
    if not req:
        return None, "request_not_found"
    if req["status"] != "pending":
        return None, "already_processed"

    code = _gen_code()
    url = SUPABASE_URL + "/rest/v1/unlock_requests?id=eq." + request_id
    payload = {
        "status": "paid",
        "code": code,
        "paid_at": datetime.now(timezone.utc).isoformat()
    }
    async with httpx.AsyncClient() as client:
        r = await client.patch(url, headers=_headers(), json=payload)
        if r.status_code not in (200, 204):
            return None, "update_failed"

    return code, None


async def redeem_code(code: str, device_id: str):
    """Пользователь вводит код на сайте. Проверяем и выполняем действие."""
    url = SUPABASE_URL + "/rest/v1/unlock_requests?code=eq." + code + "&select=*"
    async with httpx.AsyncClient() as client:
        r = await client.get(url, headers=_headers())
        if r.status_code != 200 or not r.json():
            return {"ok": False, "error": "invalid_code"}
        req = r.json()[0]

    if req["status"] != "paid":
        return {"ok": False, "error": "code_not_active"}

    if req["device_id"] != device_id:
        return {"ok": False, "error": "device_mismatch"}

    result = {"ok": True, "type": req["type"]}

    async with httpx.AsyncClient() as client:
        if req["type"] == "unlock":
            target_user_id = req["target_user_id"]
            if not target_user_id:
                return {"ok": False, "error": "no_target_user"}

            # 1. Снимаем блокировку профиля
            await client.patch(
                SUPABASE_URL + "/rest/v1/profiles?id=eq." + target_user_id,
                headers=_headers(),
                json={"blocked": False}
            )

            # 2. Генерируем новый временный пароль через Supabase Admin API
            temp_password = _gen_code(10)
            admin_r = await client.put(
                SUPABASE_URL + "/auth/v1/admin/users/" + target_user_id,
                headers=_headers(),
                json={"password": temp_password}
            )
            if admin_r.status_code not in (200, 201):
                return {"ok": False, "error": "password_reset_failed"}

            result["temp_password"] = temp_password
            result["user_id"] = target_user_id

        elif req["type"] == "extra_account":
            # Разрешаем зарегистрировать ещё один аккаунт на этом устройстве.
            # Сайт при регистрации проверит наличие неиспользованной "paid" заявки
            # типа extra_account для своего device_id — если есть, регистрация разрешена,
            # а после успешной регистрации сайт сам помечает заявку использованной
            # (вызовом /api/unlock/consume).
            pass

        # Помечаем заявку использованной (для unlock — сразу;
        # для extra_account — сайт подтвердит отдельным вызовом после регистрации)
        if req["type"] == "unlock":
            await client.patch(
                SUPABASE_URL + "/rest/v1/unlock_requests?id=eq." + req["id"],
                headers=_headers(),
                json={"status": "used", "used_at": datetime.now(timezone.utc).isoformat()}
            )

    return result


async def consume_extra_account_request(code: str, device_id: str, new_user_id: str):
    """Вызывается сайтом ПОСЛЕ успешной регистрации нового аккаунта по коду extra_account."""
    url = SUPABASE_URL + "/rest/v1/unlock_requests?code=eq." + code + "&select=*"
    async with httpx.AsyncClient() as client:
        r = await client.get(url, headers=_headers())
        if r.status_code != 200 or not r.json():
            return False
        req = r.json()[0]

        if req["status"] != "paid" or req["device_id"] != device_id or req["type"] != "extra_account":
            return False

        await client.patch(
            SUPABASE_URL + "/rest/v1/unlock_requests?id=eq." + req["id"],
            headers=_headers(),
            json={"status": "used", "used_at": datetime.now(timezone.utc).isoformat()}
        )

        # Привязываем новый аккаунт к этому же устройству
        await client.post(
            SUPABASE_URL + "/rest/v1/device_accounts",
            headers=_headers(),
            json={"device_id": device_id, "user_id": new_user_id}
        )

    return True

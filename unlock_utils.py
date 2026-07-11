# unlock_utils.py
# Только логика доп.аккаунтов Blizko. "Забыл пароль" убран полностью.

import os
import secrets
import string
import re
import httpx
from datetime import datetime, timezone

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
RESUME_BOT_URL = os.environ.get("RESUME_BOT_URL", "").rstrip("/")

DEFAULT_PRICE_EXTRA_BASE = 200


def _headers():
    return {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": "Bearer " + SUPABASE_SERVICE_KEY,
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }


def _gen_code(length=8):
    alphabet = string.ascii_uppercase + string.digits
    alphabet = alphabet.replace("0", "").replace("O", "").replace("1", "").replace("I", "")
    return "".join(secrets.choice(alphabet) for _ in range(length))


async def get_extra_base_price():
    if not RESUME_BOT_URL:
        return DEFAULT_PRICE_EXTRA_BASE
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(RESUME_BOT_URL + "/api/blizko-prices", timeout=10.0)
            if r.status_code == 200:
                return int(r.json().get("extra_base_price", DEFAULT_PRICE_EXTRA_BASE))
    except Exception as e:
        print("Не удалось получить цену от resume-bot:", e)
    return DEFAULT_PRICE_EXTRA_BASE


async def count_device_accounts(device_id: str):
    url = SUPABASE_URL + "/rest/v1/device_accounts?device_id=eq." + device_id + "&select=id"
    async with httpx.AsyncClient() as client:
        r = await client.get(url, headers=_headers())
        if r.status_code != 200:
            return 0
        return len(r.json())


async def list_device_accounts(device_id: str):
    """Список email всех аккаунтов, зарегистрированных на этом устройстве (для выбора при входе)."""
    url = (SUPABASE_URL + "/rest/v1/device_accounts?device_id=eq." + device_id
           + "&select=email,created_at&order=created_at.asc")
    async with httpx.AsyncClient() as client:
        r = await client.get(url, headers=_headers())
        if r.status_code != 200:
            return []
        return [row["email"] for row in r.json() if row.get("email")]


async def link_device_account(device_id: str, user_id: str, email: str):
    """Вызывается сайтом сразу после регистрации — привязывает аккаунт к устройству."""
    url = SUPABASE_URL + "/rest/v1/device_accounts"
    async with httpx.AsyncClient() as client:
        r = await client.post(url, headers=_headers(), json={
            "device_id": device_id, "user_id": user_id, "email": email
        })
        return r.status_code in (200, 201)


async def find_pending_request(device_id: str):
    """Если у устройства уже есть неоплаченная заявка на доп.аккаунт — возвращаем её,
    чтобы не плодить новые записи и не позволять сбрасывать/пересчитывать цену повторными нажатиями."""
    url = (SUPABASE_URL + "/rest/v1/unlock_requests?device_id=eq." + device_id
           + "&type=eq.extra_account&status=eq.pending&select=*&order=created_at.desc&limit=1")
    async with httpx.AsyncClient() as client:
        r = await client.get(url, headers=_headers())
        if r.status_code != 200:
            return None
        rows = r.json()
        return rows[0] if rows else None


async def create_extra_account_request(device_id: str):
    """Создаёт заявку на доп.аккаунт. Цена = базовая × 2^(сколько уже куплено на этом устройстве).
    Если есть неоплаченная заявка — отдаём её же, а не создаём новую."""
    bot_username = os.environ.get("RESUME_BOT_USERNAME", "Rezumeizi_bot")

    pending = await find_pending_request(device_id)
    if pending:
        link = "https://t.me/" + bot_username + "?start=e_" + pending["id"]
        return pending["id"], link, pending["price"]

    base_price = await get_extra_base_price()
    existing_count = await count_device_accounts(device_id)
    price = base_price * (2 ** existing_count)

    payload = {
        "type": "extra_account",
        "device_id": device_id,
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
    # Ссылка, которую пользователь копирует и вставляет в резюме-бот
    bot_username = os.environ.get("RESUME_BOT_USERNAME", "Rezumeizi_bot")
    link = "https://t.me/" + bot_username + "?start=e_" + request_id
    return request_id, link, price


REQUEST_ID_RE = re.compile(r"e_([a-zA-Z0-9\-]+)")


def extract_request_id(pasted_text: str):
    """Достаёт request_id из вставленной пользователем ссылки (или сырого id)."""
    m = REQUEST_ID_RE.search(pasted_text.strip())
    if m:
        return m.group(1)
    cleaned = pasted_text.strip()
    if re.fullmatch(r"[a-zA-Z0-9\-]{8,}", cleaned):
        return cleaned
    return None


async def get_unlock_request(request_id: str):
    url = SUPABASE_URL + "/rest/v1/unlock_requests?id=eq." + request_id + "&select=*"
    async with httpx.AsyncClient() as client:
        r = await client.get(url, headers=_headers())
        if r.status_code != 200:
            return None
        rows = r.json()
        return rows[0] if rows else None


async def mark_request_paid(request_id: str):
    """Бот вызывает после успешной оплаты. Генерирует код, отдаёт его боту для показа пользователю."""
    req = await get_unlock_request(request_id)
    if not req:
        return None, "request_not_found"
    if req["status"] != "pending":
        return None, "already_processed"

    code = _gen_code()
    url = SUPABASE_URL + "/rest/v1/unlock_requests?id=eq." + request_id
    payload = {"status": "paid", "code": code, "paid_at": datetime.now(timezone.utc).isoformat()}
    async with httpx.AsyncClient() as client:
        r = await client.patch(url, headers=_headers(), json=payload)
        if r.status_code not in (200, 204):
            return None, "update_failed"

    return code, None


async def redeem_code(code: str, device_id: str):
    """Пользователь вставляет код на сайте — разрешаем регистрацию доп.аккаунта."""
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

    return {"ok": True, "type": "extra_account"}


async def consume_extra_account_request(code: str, device_id: str, new_user_id: str, email: str):
    """Вызывается сайтом ПОСЛЕ успешной регистрации нового аккаунта по коду."""
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
        await client.post(
            SUPABASE_URL + "/rest/v1/device_accounts",
            headers=_headers(),
            json={"device_id": device_id, "user_id": new_user_id, "email": email}
        )
    return True

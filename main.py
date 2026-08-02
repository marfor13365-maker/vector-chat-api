from fastapi import FastAPI, UploadFile, File, HTTPException, Query, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import psycopg2
import os
import uuid
import base64
import httpx
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from push_utils import send_push_to_user
from moderation_utils import moderate_image, moderate_video
from unlock_utils import (
    supabase_insert,
    count_profile_photos,
    create_extra_account_request,
    get_unlock_request,
    mark_request_paid,
    redeem_code,
    consume_extra_account_request,
    link_device_account,
    list_device_accounts,
    get_user_id_from_token,
    delete_auth_user,
)

app = FastAPI()

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DB = os.environ.get("DATABASE_URL")
GROQ_KEY = os.environ.get("GROQ_KEY")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
INTERNAL_API_KEY = os.environ.get("INTERNAL_API_KEY", "")

def get_conn():
    return psycopg2.connect(DB)

def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS chats (
            id TEXT PRIMARY KEY,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id TEXT PRIMARY KEY,
            chat_id TEXT,
            role TEXT,
            content TEXT,
            file_url TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    conn.commit()
    cur.close()
    conn.close()

init_db()

class Message(BaseModel):
    chat_id: str
    role: str
    content: str = ""

class ChatRequest(BaseModel):
    messages: list

class AdminLogin(BaseModel):
    password: str

class GroqRequest(BaseModel):
    password: str
    messages: list
    persona: str = ""

class SendPushRequest(BaseModel):
    to_user_id: str
    title: str
    body: str
    type: str = "message"
    callId: Optional[str] = None
    fromUserId: Optional[str] = None
    url: Optional[str] = None

class CreateExtraAccountRequest(BaseModel):
    device_id: str

class MarkPaidRequest(BaseModel):
    request_id: str

class RedeemCodeRequest(BaseModel):
    code: str
    device_id: str

class ConsumeExtraRequest(BaseModel):
    code: str
    device_id: str
    new_user_id: str
    email: str

class LinkDeviceRequest(BaseModel):
    device_id: str
    user_id: str
    email: str

class DeleteAccountRequest(BaseModel):
    user_id: str
    access_token: str

class CreatePostRequest(BaseModel):
    user_id: str
    access_token: str
    photo_url: str
    media_type: str = "photo"  # "photo" или "video"
    caption: str = ""
    also_feed: bool = False
    profile_photo_id: Optional[str] = None  # если публикуем уже существующее фото в ленту

class CallNotifyRequest(BaseModel):
    to_user_id: str
    from_user_id: str
    access_token: str
    caller_name: str = "Пользователь"
    call_id: str
    match_id: str

class ModerateRequest(BaseModel):
    photo_url: str
    media_type: str = "photo"  # "photo" или "video"

@app.get("/")
def root():
    return {"status": "ok"}

@app.post("/chat")
async def chat(req: ChatRequest):
    async with httpx.AsyncClient() as client:
        r = await client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"},
            json={"model": "llama-3.1-8b-instant", "messages": req.messages},
            timeout=30.0
        )
        return r.json()

@app.post("/chats")
def create_chat():
    chat_id = str(uuid.uuid4())
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("INSERT INTO chats (id) VALUES (%s)", (chat_id,))
    conn.commit()
    cur.close()
    conn.close()
    return {"chat_id": chat_id}

@app.post("/messages")
def save_message(msg: Message):
    msg_id = str(uuid.uuid4())
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO messages (id, chat_id, role, content) VALUES (%s, %s, %s, %s)",
        (msg_id, msg.chat_id, msg.role, msg.content)
    )
    conn.commit()
    cur.close()
    conn.close()
    return {"id": msg_id}

@app.get("/messages/{chat_id}")
def get_messages(chat_id: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, role, content, file_url FROM messages WHERE chat_id=%s ORDER BY created_at",
        (chat_id,)
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [{"id": r[0], "role": r[1], "content": r[2], "file_url": r[3]} for r in rows]

@app.get("/admin/chats")
def get_all_chats(password: str = Query(...)):
    admin_pass = os.environ.get("ADMIN_PASSWORD", "Papuas13")
    if password != admin_pass:
        raise HTTPException(status_code=403, detail="Wrong password")
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT c.id, c.created_at,
            (SELECT content FROM messages WHERE chat_id=c.id ORDER BY created_at DESC LIMIT 1) as last_msg
        FROM chats c ORDER BY c.created_at DESC
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [{"id": r[0], "created_at": str(r[1]), "last_msg": r[2]} for r in rows]

@app.get("/admin/messages/{chat_id}")
def get_chat_messages(chat_id: str, password: str = Query(...)):
    admin_pass = os.environ.get("ADMIN_PASSWORD", "Papuas13")
    if password != admin_pass:
        raise HTTPException(status_code=403, detail="Wrong password")
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT role, content, file_url, created_at FROM messages WHERE chat_id=%s ORDER BY created_at",
        (chat_id,)
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [{"role": r[0], "content": r[1], "file_url": r[2], "time": str(r[3])} for r in rows]

@app.delete("/admin/chat/{chat_id}")
def delete_chat(chat_id: str, password: str = Query(...)):
    admin_pass = os.environ.get("ADMIN_PASSWORD", "Papuas13")
    if password != admin_pass:
        raise HTTPException(status_code=403, detail="Wrong password")
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM messages WHERE chat_id=%s", (chat_id,))
    cur.execute("DELETE FROM chats WHERE id=%s", (chat_id,))
    conn.commit()
    cur.close()
    conn.close()
    return {"status": "deleted"}

@app.post("/upload/{chat_id}")
async def upload_file(chat_id: str, file: UploadFile = File(...)):
    data = await file.read()
    b64 = base64.b64encode(data).decode()
    file_url = f"data:{file.content_type};base64,{b64}"
    msg_id = str(uuid.uuid4())
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO messages (id, chat_id, role, file_url) VALUES (%s, %s, %s, %s)",
        (msg_id, chat_id, "user", file_url)
    )
    conn.commit()
    cur.close()
    conn.close()
    return {"id": msg_id, "file_url": file_url}

@app.post("/blizko/login")
def blizko_login(req: AdminLogin):
    admin_pass = os.environ.get("BLIZKO_ADMIN_PASS", "admin2024")
    if req.password != admin_pass:
        raise HTTPException(status_code=403, detail="Wrong password")
    return {"ok": True}

@app.get("/blizko/config")
def blizko_config(password: str = Query(...)):
    admin_pass = os.environ.get("BLIZKO_ADMIN_PASS", "admin2024")
    if password != admin_pass:
        raise HTTPException(status_code=403, detail="Wrong password")
    return {"supabase_url": SUPABASE_URL or "", "supabase_key": SUPABASE_KEY or ""}

@app.post("/blizko/groq")
async def blizko_groq(req: GroqRequest):
    admin_pass = os.environ.get("BLIZKO_ADMIN_PASS", "admin2024")
    if req.password != admin_pass:
        raise HTTPException(status_code=403, detail="Wrong password")
    msgs = []
    if req.persona:
        msgs.append({"role": "system", "content": req.persona})
    msgs.extend(req.messages)
    async with httpx.AsyncClient() as client:
        r = await client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"},
            json={"model": "llama-3.1-8b-instant", "messages": msgs, "max_tokens": 200},
            timeout=30.0
        )
        return r.json()

@app.post("/api/send-push")
async def api_send_push(req: SendPushRequest, x_api_key: str = Header(None)):
    if not INTERNAL_API_KEY or x_api_key != INTERNAL_API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")
    payload = {
        "title": req.title, "body": req.body, "type": req.type,
        "callId": req.callId, "fromUserId": req.fromUserId, "url": req.url or "/"
    }
    result = await send_push_to_user(req.to_user_id, payload)
    return result

# ── Привязка аккаунта к устройству (сайт вызывает сразу после регистрации) ──

@app.post("/api/device/link-account")
@limiter.limit("10/minute")
async def api_link_device_account(req: LinkDeviceRequest, request: Request):
    client_ip = request.client.host if request.client else None
    ok, error = await link_device_account(req.device_id, req.user_id, req.email, client_ip)
    if not ok:
        raise HTTPException(status_code=400, detail=error or "link_failed")
    return {"ok": True}

@app.get("/api/device/accounts/{device_id}")
async def api_device_accounts(device_id: str):
    """Список email всех аккаунтов на этом устройстве — сайт показывает при входе."""
    emails = await list_device_accounts(device_id)
    return {"emails": emails}

@app.post("/api/account/delete")
@limiter.limit("5/minute")
async def api_delete_account(req: DeleteAccountRequest, request: Request):
    """По-настоящему удаляет аккаунт из auth.users (обычный клиентский ключ так не умеет).
    Сначала проверяем, что access_token реально принадлежит этому user_id — иначе
    кто угодно мог бы удалить чужой аккаунт, просто зная его id."""
    verified_id = await get_user_id_from_token(req.access_token)
    if not verified_id or verified_id != req.user_id:
        raise HTTPException(status_code=403, detail="token_mismatch")

    ok = await delete_auth_user(req.user_id)
    if not ok:
        raise HTTPException(status_code=400, detail="delete_failed")
    return {"ok": True}

# ── Доп.аккаунт через код из резюме-бота (оплата за "забыл пароль" убрана полностью) ──

@app.post("/api/unlock/create-request")
@limiter.limit("5/minute")
async def api_create_extra_request(req: CreateExtraAccountRequest, request: Request):
    request_id, link, price = await create_extra_account_request(req.device_id)
    return {"request_id": request_id, "telegram_link": link, "price": price}


@app.get("/api/unlock/status/{request_id}")
async def api_unlock_status(request_id: str):
    req = await get_unlock_request(request_id)
    if not req:
        raise HTTPException(status_code=404, detail="not_found")
    return {
        "status": req["status"],
        "type": req["type"],
        "price": req["price"],
        "code": req["code"] if req["status"] in ("paid", "used") else None
    }


@app.post("/api/unlock/mark-paid")
async def api_mark_paid(req: MarkPaidRequest, x_api_key: str = Header(None)):
    if not INTERNAL_API_KEY or x_api_key != INTERNAL_API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")
    code, error = await mark_request_paid(req.request_id)
    if error:
        raise HTTPException(status_code=400, detail=error)
    return {"code": code}


@app.post("/api/unlock/redeem")
@limiter.limit("10/minute")
async def api_redeem_code(req: RedeemCodeRequest, request: Request):
    result = await redeem_code(req.code, req.device_id)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error", "unknown_error"))
    return result


@app.post("/api/posts/create")
@limiter.limit("20/minute")
async def api_create_post(req: CreatePostRequest, request: Request):
    verified_id = await get_user_id_from_token(req.access_token)
    if not verified_id or verified_id != req.user_id:
        raise HTTPException(status_code=403, detail="token_mismatch")

    # Модерация только для того, что реально попадёт в ленту (posts) —
    # приватные фото/видео в галерее профиля (не идущие в ленту) не проверяются.
    going_to_feed = bool(req.also_feed) or bool(req.profile_photo_id)
    if going_to_feed:
        if req.media_type == "video":
            is_safe, reason = await moderate_video(req.photo_url)
        else:
            is_safe, reason = await moderate_image(req.photo_url)
        if not is_safe:
            raise HTTPException(status_code=400, detail="content_rejected: " + reason)

    if req.profile_photo_id:
        # публикация уже существующего фото профиля в ленту
        row = await supabase_insert("posts", {
            "user_id": req.user_id,
            "photo_url": req.photo_url,
            "caption": req.caption,
            "media_type": req.media_type,
            "profile_photo_id": req.profile_photo_id
        })
        return {"ok": True, "post": row}

    existing_count = await count_profile_photos(req.user_id)
    photo_row = await supabase_insert("profile_photos", {
        "user_id": req.user_id,
        "photo_url": req.photo_url,
        "media_type": req.media_type,
        "position": existing_count
    })

    if req.also_feed:
        await supabase_insert("posts", {
            "user_id": req.user_id,
            "photo_url": req.photo_url,
            "caption": req.caption,
            "media_type": req.media_type,
            "profile_photo_id": photo_row["id"]
        })

    return {"ok": True, "profile_photo": photo_row}


@app.post("/api/moderate")
@limiter.limit("30/minute")
async def api_moderate(req: ModerateRequest, request: Request):
    """Лёгкий эндпоинт ТОЛЬКО для проверки контента — без побочных эффектов (ничего
    никуда не пишет). Добавлен отдельно от /api/posts/create, потому что фронтенд
    сейчас публикует посты напрямую через Supabase-клиент (в обход /api/posts/create),
    из-за чего модерация фактически не вызывалась ни разу. Фронтенд должен звать этот
    эндпоинт непосредственно перед тем, как что-либо публикуется в ленту (posts), и
    отменять публикацию, если safe=false."""
    if req.media_type == "video":
        is_safe, reason = await moderate_video(req.photo_url)
    else:
        is_safe, reason = await moderate_image(req.photo_url)
    return {"safe": is_safe, "reason": reason}


# ── Push-уведомление о входящем звонке (сайт вызывает при старте звонка) ──

@app.post("/api/calls/notify")
@limiter.limit("20/minute")
async def api_calls_notify(req: CallNotifyRequest, request: Request):
    """Отправляет push 'входящий звонок'. Проверяем access_token, чтобы нельзя было
    отправить звонок от чужого имени, просто зная user_id."""
    verified_id = await get_user_id_from_token(req.access_token)
    if not verified_id or verified_id != req.from_user_id:
        raise HTTPException(status_code=403, detail="token_mismatch")

    # Проверяем, не отключил ли получатель уведомления о звонках
    async with httpx.AsyncClient() as client:
        prof_r = await client.get(
            SUPABASE_URL + "/rest/v1/profiles?id=eq." + req.to_user_id + "&select=notif_calls",
            headers={"apikey": SUPABASE_KEY, "Authorization": "Bearer " + SUPABASE_KEY}
        )
        if prof_r.status_code == 200 and prof_r.json():
            if prof_r.json()[0].get("notif_calls") is False:
                return {"sent": 0, "reason": "notifications_disabled_by_user"}

    payload = {
        "title": "Входящий звонок",
        "body": req.caller_name + " звонит вам",
        "type": "call",
        "callId": req.call_id,
        "fromUserId": req.from_user_id,
        "url": "/matches.html?incoming_call=" + req.call_id + "&match=" + req.match_id
    }
    result = await send_push_to_user(req.to_user_id, payload)
    return result

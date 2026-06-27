from fastapi import FastAPI, UploadFile, File, HTTPException, Query, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import psycopg2
import os
import uuid
import base64
import httpx

from push_utils import send_push_to_user

app = FastAPI()

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
    type: str = "message"      # "message" или "call"
    callId: Optional[str] = None
    fromUserId: Optional[str] = None
    url: Optional[str] = None

@app.get("/")
def root():
    return {"status": "ok"}

@app.post("/chat")
async def chat(req: ChatRequest):
    async with httpx.AsyncClient() as client:
        r = await client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "llama-3.1-8b-instant",
                "messages": req.messages
            },
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

# ── Blizko Admin endpoints ──

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
    return {
        "supabase_url": SUPABASE_URL or "",
        "supabase_key": SUPABASE_KEY or ""
    }

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
            headers={
                "Authorization": f"Bearer {GROQ_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "llama-3.1-8b-instant",
                "messages": msgs,
                "max_tokens": 200
            },
            timeout=30.0
        )
        return r.json()

# ── Push-уведомления (звонки / сообщения в Blizko) ──

@app.post("/api/send-push")
async def api_send_push(req: SendPushRequest, x_api_key: str = Header(None)):
    if not INTERNAL_API_KEY or x_api_key != INTERNAL_API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")

    payload = {
        "title": req.title,
        "body": req.body,
        "type": req.type,
        "callId": req.callId,
        "fromUserId": req.fromUserId,
        "url": req.url or "/"
    }

    result = await send_push_to_user(req.to_user_id, payload)
    return result

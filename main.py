from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import psycopg2
import os
import uuid
import base64

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DB = os.environ.get("DATABASE_URL")

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

@app.get("/")
def root():
    return {"status": "ok"}

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
        "SELECT id, role, content, file_url, created_at FROM messages WHERE chat_id=%s ORDER BY created_at",
        (chat_id,)
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [{"id": r[0], "role": r[1], "content": r[2], "file_url": r[3]} for r in rows]

@app.get("/admin/chats")
def get_all_chats():
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

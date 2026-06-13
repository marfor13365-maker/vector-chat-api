<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Админ — Студия Вектор</title>
<style>
:root{--black:#0a0a0a;--dark:#111318;--card:#16191f;--accent:#00e5ff;--white:#f0f4f8;--muted:#8a9ab0;--border:rgba(0,229,255,0.12)}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Segoe UI',sans-serif;background:var(--black);color:var(--white);min-height:100vh}
.login{display:flex;align-items:center;justify-content:center;min-height:100vh;padding:20px}
.login-box{background:var(--dark);border:1px solid var(--border);border-radius:12px;padding:40px 32px;width:100%;max-width:360px;text-align:center}
.login-box h1{font-size:24px;color:var(--accent);margin-bottom:8px;letter-spacing:2px}
.login-box p{font-size:14px;color:var(--muted);margin-bottom:28px}
.login-box input{width:100%;background:var(--card);border:1px solid var(--border);border-radius:8px;padding:12px 16px;color:var(--white);font-size:15px;outline:none;margin-bottom:16px}
.login-box input:focus{border-color:var(--accent)}
.login-box button{width:100%;background:var(--accent);color:var(--black);border:none;border-radius:8px;padding:13px;font-size:15px;font-weight:700;cursor:pointer}
.login-box button:hover{background:#fff}
.login-error{color:#ff4444;font-size:13px;margin-top:12px;display:none}

.app{display:none;height:100vh;flex-direction:column}
.app.visible{display:flex}

header{background:var(--dark);border-bottom:1px solid var(--border);padding:14px 20px;display:flex;align-items:center;justify-content:space-between;flex-shrink:0}
header h1{font-size:18px;color:var(--accent);letter-spacing:2px}
.header-right{display:flex;align-items:center;gap:12px}
.refresh-btn{background:none;border:1px solid var(--border);color:var(--muted);padding:6px 14px;border-radius:6px;font-size:13px;cursor:pointer}
.refresh-btn:hover{border-color:var(--accent);color:var(--accent)}
.logout-btn{background:none;border:1px solid rgba(255,68,68,0.3);color:#ff6666;padding:6px 14px;border-radius:6px;font-size:13px;cursor:pointer}
.logout-btn:hover{border-color:#ff4444;color:#ff4444}

.main{display:flex;flex:1;overflow:hidden}

.sidebar{width:300px;background:var(--dark);border-right:1px solid var(--border);display:flex;flex-direction:column;flex-shrink:0}
.sidebar-header{padding:16px;border-bottom:1px solid var(--border);flex-shrink:0}
.sidebar-title{font-size:13px;color:var(--muted);letter-spacing:1px;text-transform:uppercase;margin-bottom:8px}
.chat-count{font-size:22px;font-weight:700;color:var(--accent)}
.chats-list{flex:1;overflow-y:auto;padding:8px}
.chat-item{padding:12px 14px;border-radius:8px;cursor:pointer;transition:all 0.2s;border:1px solid transparent;margin-bottom:4px}
.chat-item:hover{background:var(--card);border-color:var(--border)}
.chat-item.active{background:var(--card);border-color:var(--accent)}
.chat-item-id{font-size:11px;color:var(--muted);font-family:monospace;margin-bottom:4px}
.chat-item-msg{font-size:13px;color:var(--white);line-height:1.4;overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}
.chat-item-time{font-size:11px;color:var(--muted);margin-top:4px}
.chat-item-empty{font-size:12px;color:var(--muted);font-style:italic}

.chat-panel{flex:1;display:flex;flex-direction:column;overflow:hidden}
.chat-panel-empty{flex:1;display:flex;align-items:center;justify-content:center;flex-direction:column;gap:12px;color:var(--muted)}
.chat-panel-empty .icon{font-size:48px;opacity:0.3}
.chat-panel-header{padding:14px 20px;border-bottom:1px solid var(--border);background:var(--dark);flex-shrink:0}
.chat-panel-header h3{font-size:14px;font-weight:600;margin-bottom:2px}
.chat-panel-header p{font-size:12px;color:var(--muted);font-family:monospace}
.messages-list{flex:1;overflow-y:auto;padding:16px;display:flex;flex-direction:column;gap:10px}
.msg-row{display:flex;flex-direction:column;gap:2px}
.msg-row.user{align-items:flex-end}
.msg-row.assistant{align-items:flex-start}
.msg-bubble{max-width:75%;padding:10px 14px;border-radius:12px;font-size:14px;line-height:1.5;word-break:break-word}
.msg-bubble.user{background:var(--accent);color:var(--black);border-bottom-right-radius:3px;font-weight:500}
.msg-bubble.assistant{background:var(--card);color:var(--white);border-bottom-left-radius:3px;border:1px solid var(--border)}
.msg-time{font-size:11px;color:var(--muted);padding:0 4px}
.msg-role{font-size:11px;color:var(--muted);padding:0 4px;text-transform:uppercase;letter-spacing:0.5px}

.loading{text-align:center;padding:40px;color:var(--muted);font-size:14px}
.error-msg{text-align:center;padding:40px;color:#ff6666;font-size:14px}

@media(max-width:600px){
.sidebar{width:100%;height:200px;border-right:none;border-bottom:1px solid var(--border)}
.main{flex-direction:column}
.msg-bubble{max-width:88%}
}
</style>
</head>
<body>

<!-- LOGIN -->
<div class="login" id="loginScreen">
  <div class="login-box">
    <h1>ВЕКТОР</h1>
    <p>Панель администратора</p>
    <input type="password" id="passwordInput" placeholder="Введите пароль" onkeydown="if(event.key==='Enter')doLogin()">
    <button onclick="doLogin()">Войти</button>
    <div class="login-error" id="loginError">Неверный пароль</div>
  </div>
</div>

<!-- APP -->
<div class="app" id="appScreen">
  <header>
    <h1>АДМИН ПАНЕЛЬ</h1>
    <div class="header-right">
      <button class="refresh-btn" onclick="loadChats()">🔄 Обновить</button>
      <button class="logout-btn" onclick="logout()">Выйти</button>
    </div>
  </header>
  <div class="main">
    <div class="sidebar">
      <div class="sidebar-header">
        <div class="sidebar-title">Чаты клиентов</div>
        <div class="chat-count" id="chatCount">0</div>
      </div>
      <div class="chats-list" id="chatsList">
        <div class="loading">Загрузка...</div>
      </div>
    </div>
    <div class="chat-panel" id="chatPanel">
      <div class="chat-panel-empty">
        <div class="icon">💬</div>
        <div>Выберите чат слева</div>
      </div>
    </div>
  </div>
</div>

<script>
const API = 'https://vector-chat-api.onrender.com';
let password = '';
let currentChatId = null;
let allChats = [];

function doLogin() {
  const pwd = document.getElementById('passwordInput').value.trim();
  if (!pwd) return;
  password = pwd;
  loadChats();
}

async function loadChats() {
  try {
    const r = await fetch(`${API}/admin/chats?password=${encodeURIComponent(password)}`);
    if (r.status === 403) {
      document.getElementById('loginError').style.display = 'block';
      return;
    }
    const data = await r.json();
    document.getElementById('loginScreen').style.display = 'none';
    document.getElementById('appScreen').classList.add('visible');
    allChats = data;
    renderChats(data);
  } catch(e) {
    document.getElementById('loginError').style.display = 'block';
    document.getElementById('loginError').textContent = 'Ошибка подключения к серверу';
  }
}

function renderChats(chats) {
  document.getElementById('chatCount').textContent = chats.length;
  const list = document.getElementById('chatsList');
  if (!chats.length) {
    list.innerHTML = '<div class="loading">Чатов пока нет</div>';
    return;
  }
  list.innerHTML = chats.map(c => `
    <div class="chat-item ${c.id === currentChatId ? 'active' : ''}" onclick="openChat('${c.id}')">
      <div class="chat-item-id">${c.id.substring(0,8)}...</div>
      <div class="${c.last_msg ? 'chat-item-msg' : 'chat-item-empty'}">${c.last_msg || 'Нет сообщений'}</div>
      <div class="chat-item-time">${formatTime(c.created_at)}</div>
    </div>
  `).join('');
}

async function openChat(chatId) {
  currentChatId = chatId;
  renderChats(allChats);
  const panel = document.getElementById('chatPanel');
  panel.innerHTML = '<div class="loading">Загрузка сообщений...</div>';
  try {
    const r = await fetch(`${API}/admin/messages/${chatId}?password=${encodeURIComponent(password)}`);
    const msgs = await r.json();
    const chat = allChats.find(c => c.id === chatId);
    panel.innerHTML = `
      <div class="chat-panel-header">
        <h3>Чат клиента</h3>
        <p>${chatId}</p>
      </div>
      <div class="messages-list" id="msgList">
        ${msgs.length ? msgs.map(m => `
          <div class="msg-row ${m.role}">
            <div class="msg-role">${m.role === 'user' ? '👤 Клиент' : '🤖 Ассистент'}</div>
            <div class="msg-bubble ${m.role}">${escapeHtml(m.content || '')}</div>
            <div class="msg-time">${formatTime(m.time)}</div>
          </div>
        `).join('') : '<div class="loading">Сообщений нет</div>'}
      </div>
    `;
    const msgList = document.getElementById('msgList');
    if (msgList) msgList.scrollTop = msgList.scrollHeight;
  } catch(e) {
    panel.innerHTML = '<div class="error-msg">Ошибка загрузки сообщений</div>';
  }
}

function escapeHtml(text) {
  return text.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\n/g,'<br>');
}

function formatTime(str) {
  if (!str) return '';
  try {
    const d = new Date(str);
    return d.toLocaleString('ru-RU', {day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'});
  } catch(e) { return str; }
}

function logout() {
  password = '';
  currentChatId = null;
  document.getElementById('appScreen').classList.remove('visible');
  document.getElementById('loginScreen').style.display = 'flex';
  document.getElementById('passwordInput').value = '';
  document.getElementById('loginError').style.display = 'none';
}

// Auto-refresh every 30 seconds
setInterval(() => { if (password) loadChats(); }, 30000);
</script>
</body>
</html>

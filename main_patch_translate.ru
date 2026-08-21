# ============================================================
# ПАТЧ ДЛЯ main.py — добавить эндпоинт перевода постов/комментариев
# ============================================================
#
# Ничего не переписывай в существующем main.py — просто вставь три
# блока ниже в соответствующие места файла.


# ---- БЛОК 1: добавить рядом с остальными Pydantic-моделями ----
# (после class ModerateRequest(BaseModel): ...)

class TranslateRequest(BaseModel):
    text: str
    target_lang: str = "en"  # "en" или "ru" — на какой язык переводим


# ---- БЛОК 2: добавить рядом с остальными @app.post эндпоинтами ----
# (например, сразу после @app.post("/api/moderate") ...)

@app.post("/api/translate")
@limiter.limit("30/minute")
async def api_translate(req: TranslateRequest, request: Request):
    """Переводит текст поста/комментария в ленте. Используется той же Groq LLM,
    что и /chat (llama-3.1-8b-instant) — переиспользуем существующий GROQ_KEY,
    новых переменных окружения не требуется.

    Возвращает { "translated": "..." }. При ошибке связи с Groq возвращает
    оригинальный текст без изменений (fail-open — как и в модерации), чтобы
    сбой перевода не ломал ленту для пользователя."""
    text = (req.text or "").strip()
    if not text:
        return {"translated": ""}

    target_name = "English" if req.target_lang == "en" else "Russian"
    prompt = (
        f"Translate the following text to {target_name}. "
        f"Return ONLY the translated text, with no quotes, no explanations, "
        f"and no additional commentary:\n\n{text}"
    )

    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"},
                json={
                    "model": "llama-3.1-8b-instant",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.2,
                    "max_tokens": 500
                },
                timeout=20.0
            )
            data = r.json()
            translated = data["choices"][0]["message"]["content"].strip()
            return {"translated": translated}
    except Exception as e:
        print("api_translate error (возвращаем оригинал):", e)
        return {"translated": text, "error": "translation_error"}


# ---- БЛОК 3: ничего менять не нужно ----
# GROQ_KEY уже объявлен в начале файла (os.environ.get("GROQ_KEY")),
# лимитер (limiter) уже настроен — эндпоинт просто переиспользует оба.

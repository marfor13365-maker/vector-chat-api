# moderation_utils.py
# Положи рядом с main.py в репозитории vector-chat-api.
#
# Проверяет фото/видео-превью через Groq vision-модель перед публикацией в Blizko.
# ВАЖНО: название vision-модели у Groq может со временем меняться — если получишь
# ошибку "model not found", зайди в console.groq.com/docs/models и подставь
# актуальное имя действующей vision-модели в переменную GROQ_VISION_MODEL на Render.

import os
import json
from groq import Groq

GROQ_API_KEY = os.environ.get("GROQ_KEY", "")
GROQ_VISION_MODEL = os.environ.get("GROQ_VISION_MODEL", "llama-3.2-11b-vision-preview")

_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

MODERATION_PROMPT = (
    "Ты модератор контента для социальной сети знакомств. Посмотри на изображение и определи, "
    "нарушает ли оно правила: порнография/эксплицитный сексуальный контент, контент с участием "
    "несовершеннолетних в любой форме, экстремальное насилие/жестокость, разжигание ненависти. "
    "Обычные фото людей (в том числе в купальниках/пляжная одежда), портреты, повседневные сцены "
    "разрешены и не должны блокироваться. "
    "Ответь СТРОГО в формате JSON без каких-либо пояснений: "
    '{"safe": true/false, "reason": "краткая причина на русском, если safe=false, иначе пустая строка"}'
)


async def moderate_image(image_url: str):
    """Возвращает (is_safe: bool, reason: str). При ошибке связи с Groq — пропускает
    контент (safe=True), чтобы сбой модерации не блокировал обычных пользователей;
    ошибка логируется на стороне вызывающего кода."""
    if not _client:
        return True, "moderation_disabled_no_api_key"

    try:
        response = _client.chat.completions.create(
            model=GROQ_VISION_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": MODERATION_PROMPT},
                        {"type": "image_url", "image_url": {"url": image_url}}
                    ]
                }
            ],
            max_tokens=150,
            temperature=0
        )
        raw = response.choices[0].message.content.strip()
        # Модель иногда оборачивает JSON в ```json ... ``` — на всякий случай чистим
        raw = raw.replace("```json", "").replace("```", "").strip()
        data = json.loads(raw)
        return bool(data.get("safe", True)), data.get("reason", "")
    except Exception as e:
        print("moderate_image error (пропускаем контент, не блокируем пользователя):", e)
        return True, "moderation_error"

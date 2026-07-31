# moderation_utils.py
# Положи рядом с main.py в репозитории vector-chat-api.
#
# Проверяет фото/видео через Groq vision-модель — но ТОЛЬКО контент, который публикуется
# в ленту (posts). Приватные фото в галерее профиля (не идущие в ленту) не модерируются.
#
# ФИКС: модель meta-llama/llama-4-scout-17b-16e-instruct официально снята Groq с
# эксплуатации (deprecation-анонс от 17 июня 2026, см. console.groq.com/docs/deprecations).
# Каждый вызов с этим именем модели падал с ошибкой "model not found" — а код НАМЕРЕННО
# в таком случае пропускает контент как безопасный (fail open, чтобы сбой API не блокировал
# обычных пользователей). Именно поэтому запрещённый контент стал проходить свободно —
# модерация тихо отключилась сама, без единой видимой ошибки в приложении.
# Актуальная vision-модель на Groq сейчас — qwen/qwen3.6-27b (официально рекомендованная
# замена, тот же формат запроса с image_url, менять код вызова не нужно).
#
# ВАЖНО: если на Render в переменных окружения ЯВНО задан GROQ_VISION_MODEL со старым
# значением — он имеет приоритет над дефолтом в коде ниже, и одного этого файла будет
# недостаточно. Проверь в Render Dashboard → Environment: если такая переменная есть,
# обнови её значение на qwen/qwen3.6-27b (или удали переменную вовсе, тогда возьмётся
# новый дефолт из кода).
#
# ВАЖНО #2: название vision-модели у Groq может со временем меняться СНОВА — если получишь
# ошибку "model not found" в будущем, зайди в console.groq.com/docs/models и подставь
# актуальное имя действующей vision-модели в переменную GROQ_VISION_MODEL на Render.
# Возможно, стоит также добавить алерт (лог/уведомление себе), чтобы узнавать о таких сбоях
# сразу, а не постфактум — сейчас ошибка только печатается в print(), которую никто не видит,
# если не смотреть логи Render вручную.

import os
import json
import base64
import tempfile
import subprocess
import httpx
import imageio_ffmpeg
from groq import Groq

GROQ_API_KEY = os.environ.get("GROQ_KEY", "")
GROQ_VISION_MODEL = os.environ.get("GROQ_VISION_MODEL", "qwen/qwen3.6-27b")

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


def _ask_groq_vision(image_content):
    """image_content — либо публичный URL (строка), либо data URI (base64)."""
    response = _client.chat.completions.create(
        model=GROQ_VISION_MODEL,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": MODERATION_PROMPT},
                    {"type": "image_url", "image_url": {"url": image_content}}
                ]
            }
        ],
        max_tokens=150,
        temperature=0
    )
    raw = response.choices[0].message.content.strip()
    raw = raw.replace("```json", "").replace("```", "").strip()
    data = json.loads(raw)
    return bool(data.get("safe", True)), data.get("reason", "")


async def moderate_image(image_url: str):
    """Возвращает (is_safe: bool, reason: str). При ошибке связи с Groq — пропускает
    контент (safe=True), чтобы сбой модерации не блокировал обычных пользователей;
    ошибка логируется на стороне вызывающего кода."""
    if not _client:
        return True, "moderation_disabled_no_api_key"
    try:
        return _ask_groq_vision(image_url)
    except Exception as e:
        print("moderate_image error (пропускаем контент, не блокируем пользователя):", e)
        return True, "moderation_error"


async def moderate_video(video_url: str):
    """Скачивает видео, вытаскивает один кадр (~1 секунда) через ffmpeg и проверяет его.
    Это упрощённая проверка (один кадр, не весь ролик) — компромисс между точностью и
    стоимостью/скоростью. При любой ошибке — пропускает контент, не блокируя пользователя."""
    if not _client:
        return True, "moderation_disabled_no_api_key"

    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(video_url, timeout=30.0)
            if r.status_code != 200:
                return True, "moderation_error_download"
            video_bytes = r.content

        with tempfile.NamedTemporaryFile(suffix=".mp4") as vid_f, \
             tempfile.NamedTemporaryFile(suffix=".jpg") as frame_f:
            vid_f.write(video_bytes)
            vid_f.flush()

            ffmpeg_bin = imageio_ffmpeg.get_ffmpeg_exe()
            subprocess.run(
                [ffmpeg_bin, "-y", "-i", vid_f.name, "-ss", "00:00:01.000",
                 "-vframes", "1", frame_f.name],
                check=True, capture_output=True, timeout=25
            )
            frame_f.seek(0)
            frame_bytes = frame_f.read()

        if not frame_bytes:
            return True, "moderation_error_no_frame"

        data_uri = "data:image/jpeg;base64," + base64.b64encode(frame_bytes).decode()
        return _ask_groq_vision(data_uri)
    except Exception as e:
        print("moderate_video error (пропускаем контент, не блокируем пользователя):", e)
        return True, "moderation_error"

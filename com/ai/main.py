import os
import time
import base64
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from styles import STYLES


# =========================
# Загрузка конфигурации
# =========================
BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
OUTPUT_DIR = BASE_DIR / "outputs"
OUTPUT_DIR.mkdir(exist_ok=True)

load_dotenv(dotenv_path=ENV_PATH)

API_KEY = os.getenv("YANDEX_API_KEY")
FOLDER_ID = os.getenv("YANDEX_FOLDER_ID")

if not API_KEY or not FOLDER_ID:
    raise ValueError("Не найдены YANDEX_API_KEY или YANDEX_FOLDER_ID в .env")


# =========================
# Подключение к API
# =========================
client = OpenAI(
    api_key=API_KEY,
    base_url="https://ai.api.cloud.yandex.net/v1",
    project=FOLDER_ID,
    max_retries=0,
    timeout=120.0
)


# =========================
# Формирование промпта
# =========================
def build_prompt(user_description: str, style_key: str) -> str:
    if style_key not in STYLES:
        raise ValueError(
            f"Неизвестный стиль: {style_key}. Доступные: {', '.join(STYLES.keys())}"
        )

    style_description = STYLES[style_key]

    prompt = (
        f"Создай профессиональный тату-эскиз. "
        f"Сюжет: {user_description}. "
        f"{style_description} "
        f"Изображение должно быть расположено по центру. "
        f"Белый чистый фон. "
        f"Без кожи, без частей тела, без фотореалистичной сцены, без текста, без рамок. "
        f"Только тату-эскиз, пригодный как шаблон для мастера."
    )

    return prompt


# =========================
# Генерация изображения
# =========================
def generate_tattoo_sketch(
    user_description: str,
    style_key: str,
    output_name: str | None = None,
    size: str = "1024x1024"
) -> str:
    prompt = build_prompt(user_description, style_key)

    print("\n=== Генерация началась ===")
    print("Описание:", user_description)
    print("Стиль:", style_key)
    print("Промпт:", prompt)

    start_time = time.perf_counter()

    response = client.images.generate(
        model=f"art://{FOLDER_ID}/aliceai-image-art-3.0",
        prompt=prompt,
        size=size
    )

    image_bytes = base64.b64decode(response.data[0].b64_json)

    if output_name is None:
        safe_style = style_key.replace(" ", "_")
        output_name = f"{safe_style}_{int(time.time())}.png"

    output_path = OUTPUT_DIR / output_name

    with open(output_path, "wb") as file:
        file.write(image_bytes)

    elapsed = time.perf_counter() - start_time

    print("=== Генерация завершена ===")
    print(f"Файл сохранён: {output_path}")
    print(f"Время генерации: {elapsed:.2f} сек")

    return str(output_path)


# =========================
# Пример запуска
# =========================
if __name__ == "__main__":
    description = "чёрная змея, обвивающая розу"
    style = "minimalism"

    generate_tattoo_sketch(
        user_description=description,
        style_key=style,
        output_name="snake_rose_minimalism.png"
    )
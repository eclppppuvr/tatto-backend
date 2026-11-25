
import os
import time
import base64

from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

# Указываем точный путь к .env
env_path = Path(__file__).resolve().parent / ".env"

print("Путь к .env:", env_path)
print("Файл существует:", env_path.is_file())

load_dotenv(dotenv_path=env_path)

api_key = os.getenv("YANDEX_API_KEY")
folder_id = os.getenv("YANDEX_FOLDER_ID")

print("API-ключ найден:", bool(api_key))
print("Folder ID найден:", bool(folder_id))


if not api_key or not folder_id:
    raise ValueError("Проверь API-ключ и Folder ID в .env")

# Подключаемся к Yandex AI Studio
client = OpenAI(
    api_key=api_key,
    base_url="https://ai.api.cloud.yandex.net/v1",
    project=folder_id,
    max_retries=0,
    timeout=120.0
)

# Первый тестовый промпт
prompt = (
    "Тату-эскиз: чёрная змея, обвивающая розу. "
    "Стиль минимализм. Чёткие тонкие контурные линии. "
    "Без теней, без заливки. Рисунок по центру, "
    "на чистом белом фоне. Без кожи, тела и текста."
)

print("Начинаем генерацию...")
start = time.perf_counter()

# Один запрос к модели
response = client.images.generate(
    model=f"art://{folder_id}/aliceai-image-art-3.0",
    prompt=prompt,
    size="1024x1024"
)

# Декодируем изображение
image_bytes = base64.b64decode(
    response.data[0].b64_json
)

# Сохраняем результат
with open("test_tattoo.png", "wb") as file:
    file.write(image_bytes)

elapsed = time.perf_counter() - start

print("Генерация завершена!")
print(f"Время: {elapsed:.2f} секунд")
print("Файл: test_tattoo.png")

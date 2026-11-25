"""Explicit, single-request AI edits. No automatic retries or disk storage."""
import base64
from io import BytesIO
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from PIL import Image


MODEL = "gpt-image-2.5-sunburst"
PROMPT = """Create a clean, flat tattoo design on a pure white background.
Image 1 is the original tattoo photograph and is the authoritative design reference.
Image 2 is an imperfect computer-extracted draft, only a secondary guide; it may
contain shadows, hairs, lost lines and other segmentation errors.
Extract only the tattoo, remove skin texture, hair, lighting, shadows and photographic
background. Refine jagged contours and reconnect tiny clearly identifiable breaks.
Preserve the original composition, motifs, proportions and distinctive line details.
Produce crisp black ink on white, with comfortable white margins, no text or watermark.
Do not invent new motifs, replace the design or add decorative elements. Do not infer
large occluded parts. If a detail is ambiguous, preserve visible evidence rather than
creatively reinterpret it. Return only the finished design image, not a comparison."""


class AIError(RuntimeError):
    pass


def refine(photo: bytes, sketch: bytes, api_key: str, instruction: str = "",
           quality: str = "medium") -> bytes:
    if not api_key.strip():
        raise AIError("Введите API-ключ OpenAI в поле интерфейса.")
    if quality not in ("medium", "high"):
        raise AIError("Неизвестное качество обработки.")
    payload = {
        "model": MODEL,
        "images": [{"image_url": "data:image/png;base64," + base64.b64encode(data).decode("ascii")}
                   for data in (photo, sketch)],
        "prompt": PROMPT + ("\nAdditional user instructions: " + instruction[:2000] if instruction else ""),
        "n": 1, "size": "1024x1024", "quality": quality,
        "background": "opaque", "output_format": "png",
    }
    request = Request("https://api.openai.com/v1/images/edits",
                      data=json.dumps(payload).encode("utf-8"), method="POST",
                      headers={"Authorization": "Bearer " + api_key.strip(),
                               "Content-Type": "application/json"})
    try:
        with urlopen(request, timeout=300) as response:
            result = json.load(response)
    except HTTPError as error:
        messages = {401: "API-ключ не принят.", 403: "Нет доступа к модели. Проверьте права и доступность API для аккаунта.",
                    429: "Исчерпана квота или превышен лимит. Проверьте баланс и лимиты API."}
        raise AIError(messages.get(error.code, f"OpenAI API вернул HTTP {error.code}. Попробуйте позже.")) from None
    except (TimeoutError, URLError, OSError):
        raise AIError("Нет ответа от API. Запрос не повторён автоматически: он мог быть обработан и оплачен.") from None
    except ValueError:
        raise AIError("API вернул нечитаемый ответ. Автоматического повтора не было.") from None
    try:
        data = base64.b64decode(result["data"][0]["b64_json"], validate=True)
        with Image.open(BytesIO(data)) as image:
            image.load()
            output = BytesIO()
            image.convert("RGB").save(output, format="PNG")
        return output.getvalue()
    except (KeyError, IndexError, TypeError, ValueError, OSError):
        raise AIError("API не вернул корректное изображение. Повторная отправка выполняется только вручную.") from None

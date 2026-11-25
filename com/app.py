from io import BytesIO
from zipfile import ZipFile
import hashlib
import os

import cv2
import numpy as np
from PIL import Image, UnidentifiedImageError
import streamlit as st

from tattoo import extract, enhance, png, read_photo
from ai_refine import refine, AIError, MODEL

st.set_page_config(page_title="AI Tattoo Studio · Прототип", page_icon="✒️", layout="wide")
st.title("AI Tattoo Studio")
st.caption("Локальный прототип • выделение тёмного пигмента с фотографии")
st.info("Лучше всего подходят чёрные контурные татуировки. Выделите участок кожи без одежды и фона. "
        "Цветные и светлые чернила, волосы, тени и изгибы кожи требуют ручной доработки.")
photo = st.file_uploader("Фото татуировки", type=["jpg", "jpeg", "png", "webp"])
if photo is None:
    st.write("Загрузите фото или включите пример, чтобы проверить обработку.")
    if not st.checkbox("Показать синтетический пример"):
        st.stop()
    rgb = np.full((500, 700, 3), (210, 166, 140), dtype=np.uint8)
    cv2.ellipse(rgb, (350, 245), (100, 140), 20, 0, 360, (30, 27, 25), 7)
    cv2.line(rgb, (250, 330), (440, 145), (30, 27, 25), 6)
else:
    try:
        if photo.size > 20 * 1024 * 1024:
            raise ValueError("Максимальный размер файла — 20 МБ.")
        rgb = read_photo(photo.getvalue())
    except (ValueError, UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
        st.error(f"Не удалось прочитать изображение: {error}")
        st.stop()

h, w = rgb.shape[:2]
with st.sidebar:
    st.header("Область и параметры")
    st.caption(f"Рабочее изображение: {w} × {h} px. Большие фото уменьшены до 1600 px.")
    x0, x1 = st.slider("Границы по горизонтали, px", 0, w, (0, w))
    y0, y1 = st.slider("Границы по вертикали, px", 0, h, (0, h))
    threshold = st.slider("Порог пигмента", 5, 150, 30,
                          help="Меньше — больше слабых линий и шума; больше — только тёмные линии.")
    min_area = st.slider("Удалять фрагменты меньше, px", 0, 200, 8)
    size = st.slider("Размер оценки фона, px", 21, 301, 101, step=10,
                     help="Увеличьте для широких закрашенных элементов.")
    correction_file = st.file_uploader("Маска ручных правок (PNG)", type=["png"])
    st.caption("Маска размера рабочего фото: чёрный — удалить, серый 128 — автоматический результат, "
               "белый — добавить. Правки действуют внутри выбранной области.")
if x0 == x1 or y0 == y1:
    st.warning("Область должна иметь ненулевую ширину и высоту.")
    st.stop()
correction = None
try:
    if correction_file:
        with Image.open(correction_file) as im:
            if im.size != (w, h):
                raise ValueError(f"Ожидается маска {w} × {h} px.")
            correction = np.asarray(im.convert("L"))
    with st.spinner("Выделяем пигмент…"):
        result = extract(rgb, (x0, y0, x1, y1), threshold, min_area, size, correction)
except (ValueError, OSError, Image.DecompressionBombError) as error:
    st.error(str(error))
    st.stop()

preview = rgb.copy()
cv2.rectangle(preview, (x0, y0), (x1 - 1, y1 - 1), (30, 200, 130), 2)
left, right = st.columns(2)
left.image(preview, caption="Исходное фото и выбранная область", width="stretch")
right.image(result.sketch, caption="Бинарный эскиз на белом фоне", width="stretch")
with st.expander("Проверить выделение"):
    st.image(result.overlay, caption="Зелёным отмечены выбранные пиксели", width="stretch")
if not result.mask.any():
    st.warning("Пигмент не найден. Уменьшите порог или увеличьте размер оценки фона.")
assets = {f"{name}.png": png(getattr(result, name)) for name in ("sketch", "rgba", "mask", "overlay")}
st.subheader("AI-доработка по фотографии")
st.write("Модель получает выбранный участок исходного фото и черновое выделение. "
         "Она может убрать кожу и тени, уточнить контуры и восстановить небольшие разрывы.")
api_key = st.text_input("OpenAI API key", type="password", key="api_key",
                        help="Ключ остаётся в памяти текущей сессии; в файлы не записывается. Не отправляйте его в чат.")
key = api_key.strip() or os.environ.get("OPENAI_API_KEY", "")
instruction = st.text_area("Дополнительные пожелания к AI", max_chars=2000,
                           placeholder="Например: сохранить тонкие линии, убрать серые тени")
quality = st.selectbox("Качество AI-доработки", ["medium", "high"],
                       format_func=lambda v: {"medium": "Стандартное", "high": "Высокое"}[v])
photo_crop = png(rgb[y0:y1, x0:x1])
sketch_crop = png(result.sketch[y0:y1, x0:x1])
fingerprint = hashlib.sha256(photo_crop + sketch_crop + instruction.encode() + quality.encode() + MODEL.encode()).hexdigest()
if st.session_state.get("ai_source") != fingerprint:
    st.session_state.pop("ai_result", None)
    st.session_state["ai_source"] = fingerprint
st.caption("По кнопке выбранный участок фото и черновик отправятся в OpenAI. "
           "Обработка платная по тарифам API и может занять несколько минут. "
           "Модель может изменить детали — сравните результат с фото перед использованием.")
if not key:
    st.info("Для AI-доработки введите свой API-ключ выше. Без ключа доступны локальные фильтры ниже.")
if st.button("Отправить фото в OpenAI и доработать", type="primary", disabled=not key):
    try:
        with st.spinner("AI дорабатывает рисунок. Дождитесь завершения…"):
            st.session_state["ai_result"] = refine(photo_crop, sketch_crop, key, instruction, quality)
    except AIError as error:
        st.error(str(error))
if "ai_result" in st.session_state:
    a, b = st.columns(2)
    a.image(photo_crop, caption="Исходная татуировка", width="stretch")
    b.image(st.session_state["ai_result"], caption="AI-эскиз · проверьте детали рисунка", width="stretch")
    assets["ai_sketch.png"] = st.session_state["ai_result"]
    st.download_button("Скачать AI-эскиз PNG", assets["ai_sketch.png"], "ai_sketch.png", "image/png")
st.subheader("Локальная постобработка без AI")
st.caption("Локальная обработка контуров. Увеличение разрешения сглаживает края, но не восстанавливает скрытые детали.")
enabled = st.checkbox("Улучшать выделенный эскиз", value=True)
if enabled:
    with st.expander("Настройки улучшения", expanded=False):
        scale = st.select_slider("Увеличение разрешения", options=[1, 2, 4], value=2)
        noise = st.slider("Очистка отдельных точек, px", 0, 100, 6)
        gap = st.slider("Соединять разрывы, радиус px", 0, 3, 0,
                        help="Может соединить соседние линии. Начните с 1 и проверьте результат.")
        smoothing = st.slider("Сглаживание краёв", 0.0, 1.0, 0.4, 0.1)
        thickness = st.select_slider("Толщина линий", options=[-1, 0, 1], value=0,
                                    format_func=lambda v: {-1: "Тоньше", 0: "Сохранить", 1: "Толще"}[v])
        st.caption("Очистка может убрать мелкие детали; утончение — стереть тонкие линии. Сравнивайте с исходным выделением.")
    with st.spinner("Очищаем и сглаживаем контуры…"):
        improved = enhance(result.mask, scale, noise, gap, smoothing, thickness,
                           (x0, y0, x1, y1), correction)
    before, after = st.columns(2)
    before.image(result.sketch, caption="До улучшения", width="stretch")
    after.image(improved.sketch, caption=f"После улучшения · {w * scale} × {h * scale} px", width="stretch")
    assets.update({f"enhanced_{name}.png": png(getattr(improved, name))
                   for name in ("sketch", "rgba", "stencil")})
    st.download_button("Скачать улучшенный эскиз", assets["enhanced_sketch.png"],
                       "enhanced_sketch.png", "image/png")
    st.download_button("Улучшенный PNG без фона", assets["enhanced_rgba.png"],
                       "enhanced_rgba.png", "image/png")
    st.download_button("Чёрно-белый трафарет", assets["enhanced_stencil.png"],
                       "enhanced_stencil.png", "image/png")
bundle = BytesIO()
with ZipFile(bundle, "w") as archive:
    for name, data in assets.items():
        archive.writestr(name, data)
st.download_button("Скачать эскиз PNG", assets["sketch.png"], "sketch.png", "image/png")
st.download_button("Скачать все результаты ZIP", bundle.getvalue(), "tattoo-result.zip", "application/zip")
st.download_button("Шаблон маски правок", png(np.full((h, w), 128, dtype=np.uint8)),
                   "correction.png", "image/png")
st.caption("Загрузки и ключ не записываются приложением на диск. Локальные фильтры работают на этом компьютере; "
           "AI-доработка отправляет выбранную область внешнему API только по кнопке. "
           "Любой результат требует проверки мастером.")


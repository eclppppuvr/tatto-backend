"""Local dark-ink extraction. Array convention: RGB, uint8."""
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
import argparse
import json

import cv2
import numpy as np
from PIL import Image, ImageOps


@dataclass
class Result:
    sketch: np.ndarray
    rgba: np.ndarray
    mask: np.ndarray
    overlay: np.ndarray


@dataclass
class Enhanced:
    sketch: np.ndarray
    rgba: np.ndarray
    stencil: np.ndarray


def enhance(mask: np.ndarray, scale: int = 2, noise_area: int = 6,
            gap: int = 0, smoothing: float = 0.4, thickness: int = 0,
            roi=None, correction: np.ndarray | None = None) -> Enhanced:
    """Conservative raster cleanup, not generative reconstruction.

    Soft alpha preserves antialiasing; stencil is a separate binary export.
    Component sizes and gap radii are measured before upscaling.
    """
    if mask.ndim != 2 or mask.dtype != np.uint8:
        raise ValueError("Ожидается одноканальная маска uint8.")
    if scale not in (1, 2, 4) or not 0 <= gap <= 3 or not 0 <= smoothing <= 1:
        raise ValueError("Некорректные параметры улучшения.")
    if noise_area < 0 or thickness not in (-1, 0, 1):
        raise ValueError("Некорректные параметры очистки.")
    h, w = mask.shape
    clean = (mask > 127).astype(np.uint8) * 255
    count, labels, stats, _ = cv2.connectedComponentsWithStats(clean, 8)
    keep = np.zeros(count, dtype=np.uint8)
    keep[1:] = (stats[1:, cv2.CC_STAT_AREA] >= noise_area) * 255
    clean = keep[labels]
    if gap:
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (gap * 2 + 1, gap * 2 + 1))
        clean = cv2.morphologyEx(clean, cv2.MORPH_CLOSE, kernel)
    if thickness:
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        clean = (cv2.dilate if thickness > 0 else cv2.erode)(clean, kernel)
    if smoothing:
        clean = cv2.GaussianBlur(clean, (0, 0), smoothing)
    if roi is not None:
        x0, y0, x1, y1 = roi
        if not (0 <= x0 < x1 <= w and 0 <= y0 < y1 <= h):
            raise ValueError("Некорректная область улучшения.")
        allowed = np.zeros_like(clean)
        allowed[y0:y1, x0:x1] = 255
        clean = cv2.bitwise_and(clean, allowed)
    else:
        allowed = np.full_like(clean, 255)
    if correction is not None:
        if correction.shape != mask.shape:
            raise ValueError("Размер маски правок не совпадает с изображением.")
        clean[correction < 64] = 0
        clean[(correction > 192) & (allowed > 0)] = 255
    alpha = cv2.resize(clean, (w * scale, h * scale), interpolation=cv2.INTER_LANCZOS4)
    # Reapply hard exclusions at output resolution to avoid interpolation bleed.
    permitted = allowed.copy()
    if correction is not None:
        permitted[correction < 64] = 0
    alpha[cv2.resize(permitted, (w * scale, h * scale), interpolation=cv2.INTER_NEAREST) == 0] = 0
    sketch = cv2.cvtColor(255 - alpha, cv2.COLOR_GRAY2RGB)
    rgba = np.zeros((*alpha.shape, 4), dtype=np.uint8)
    rgba[:, :, 3] = alpha
    stencil = np.where(alpha >= 128, 0, 255).astype(np.uint8)
    return Enhanced(sketch, rgba, stencil)


def read_photo(data: bytes, max_side: int = 1600) -> np.ndarray:
    with Image.open(BytesIO(data)) as image:
        if image.width * image.height > 40_000_000:
            raise ValueError("Изображение слишком большое: максимум 40 Мп.")
        image = ImageOps.exif_transpose(image).convert("RGB")
        image.thumbnail((max_side, max_side))
        if min(image.size) < 32:
            raise ValueError("Минимальный размер изображения — 32 × 32 пикселя.")
        return np.asarray(image).copy()


def png(array: np.ndarray) -> bytes:
    out = BytesIO()
    Image.fromarray(array).save(out, format="PNG")
    return out.getvalue()


def extract(rgb: np.ndarray, roi=None, threshold: int = 30,
            min_area: int = 8, background_size: int = 101,
            correction: np.ndarray | None = None) -> Result:
    """Correction: 0 excludes, 128 keeps automatic mask, 255 includes ink.

    ROI uses exclusive right/bottom pixel coordinates. Output preserves the
    complete processed image canvas; pixels outside ROI are transparent/white.
    """
    if rgb.dtype != np.uint8 or rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError("Ожидается RGB uint8.")
    h, w = rgb.shape[:2]
    x0, y0, x1, y1 = roi if roi is not None else (0, 0, w, h)
    if not (0 <= x0 < x1 <= w and 0 <= y0 < y1 <= h):
        raise ValueError("Некорректная область выделения.")
    if not 1 <= threshold <= 254 or min_area < 0 or background_size < 3:
        raise ValueError("Некорректные параметры обработки.")
    crop = rgb[y0:y1, x0:x1]
    gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    # Closing estimates skin intensity beneath dark details; normalization
    # reduces gradual lighting changes. It cannot distinguish hairs from ink.
    k = background_size | 1
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    skin = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, kernel)
    deficit = 255.0 * (skin.astype(np.float32) - gray) / np.maximum(skin, 1)
    local_mask = (deficit >= threshold).astype(np.uint8) * 255
    count, labels, stats, _ = cv2.connectedComponentsWithStats(local_mask, 8)
    keep = np.zeros(count, dtype=np.uint8)
    keep[1:] = (stats[1:, cv2.CC_STAT_AREA] >= min_area) * 255
    mask = np.zeros((h, w), dtype=np.uint8)
    mask[y0:y1, x0:x1] = keep[labels]
    if correction is not None:
        if correction.shape != (h, w):
            raise ValueError("Размер маски правок должен совпадать с рабочим фото.")
        mask[correction < 64] = 0
        allowed = np.zeros((h, w), dtype=bool)
        allowed[y0:y1, x0:x1] = True
        mask[(correction > 192) & allowed] = 255
    sketch = np.full_like(rgb, 255)
    sketch[mask > 0] = 0
    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    rgba[:, :, 3] = mask
    overlay = rgb.copy()
    selected = mask > 0
    overlay[selected] = (rgb[selected] * 0.45 + np.array([30, 200, 130]) * 0.55).astype(np.uint8)
    return Result(sketch, rgba, mask, overlay)


def main():
    parser = argparse.ArgumentParser(description="Выделение тёмной татуировки на белый фон")
    parser.add_argument("photo", type=Path)
    parser.add_argument("--out", type=Path, default=Path("result"))
    parser.add_argument("--roi", type=int, nargs=4, metavar=("X0", "Y0", "X1", "Y1"))
    parser.add_argument("--threshold", type=int, default=30)
    parser.add_argument("--min-area", type=int, default=8)
    parser.add_argument("--background-size", type=int, default=101)
    args = parser.parse_args()
    rgb = read_photo(args.photo.read_bytes())
    result = extract(rgb, args.roi, args.threshold, args.min_area, args.background_size)
    args.out.mkdir(parents=True, exist_ok=True)
    for name in ("sketch", "rgba", "mask", "overlay"):
        (args.out / f"{name}.png").write_bytes(png(getattr(result, name)))
    (args.out / "parameters.json").write_text(json.dumps({
        "image_size": [rgb.shape[1], rgb.shape[0]], "roi": args.roi,
        "threshold": args.threshold, "min_area": args.min_area,
        "background_size": args.background_size,
        "selected_pixels": int(np.count_nonzero(result.mask)),
    }, indent=2), encoding="utf-8")
    print(f"Готово: {args.out.resolve()}")


if __name__ == "__main__":
    main()

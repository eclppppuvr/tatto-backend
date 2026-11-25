from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple, Union

import numpy as np
import torch
from diffusers import StableDiffusionInpaintPipeline
from PIL import Image, ImageFilter


ImageInput = Union[str, Path, Image.Image]


@dataclass
class TattooResult:
    image: Image.Image
    preview: Image.Image
    mask: Image.Image


_PIPELINE_CACHE: dict[tuple[str, str], StableDiffusionInpaintPipeline] = {}


DEFAULT_MODEL_ID = "stable-diffusion-v1-5/stable-diffusion-inpainting"
DEFAULT_PROMPT = (
    "photorealistic close-up of realistic tattoo ink naturally integrated into human skin, "
    "preserve body anatomy, preserve skin texture, preserve realistic lighting, clean tattoo edges, "
    "professional tattoo application, realistic healed black ink tattoo"
)
DEFAULT_NEGATIVE_PROMPT = (
    "deformed anatomy, extra limbs, blurry, low quality, duplicate tattoo, text, watermark, oversaturated, "
    "cartoon, painting, bad hands, distorted skin, mutated, messy ink, extra fingers"
)


def _load_image(img: ImageInput, mode: str = "RGBA") -> Image.Image:
    if isinstance(img, Image.Image):
        return img.convert(mode)
    return Image.open(img).convert(mode)


def _remove_near_white_background(img: Image.Image, threshold: int = 245) -> Image.Image:
    """Turn nearly white pixels transparent if the tattoo has no alpha channel."""
    rgba = img.convert("RGBA")
    arr = np.array(rgba)
    rgb = arr[:, :, :3]
    alpha = arr[:, :, 3]

    white_mask = (rgb[:, :, 0] >= threshold) & (rgb[:, :, 1] >= threshold) & (rgb[:, :, 2] >= threshold)
    alpha = np.where(white_mask, 0, alpha)

    # Keep dark lines opaque-ish, scale opacity by darkness for smoother blending.
    gray = rgb.mean(axis=2)
    darkness = 255 - gray
    boosted = np.clip(darkness * 1.2, 0, 255).astype(np.uint8)
    alpha = np.maximum(alpha, boosted)

    arr[:, :, 3] = alpha
    return Image.fromarray(arr, mode="RGBA")


def _resize_keep_aspect(img: Image.Image, target_width: int) -> Image.Image:
    target_width = max(8, int(target_width))
    w, h = img.size
    target_height = max(8, int(h * target_width / w))
    return img.resize((target_width, target_height), Image.LANCZOS)


def _rotate(img: Image.Image, angle: float) -> Image.Image:
    if abs(angle) < 1e-6:
        return img
    return img.rotate(angle, resample=Image.BICUBIC, expand=True)


def _build_preview_and_mask(
    body_rgb: Image.Image,
    tattoo_rgba: Image.Image,
    center_xy: Tuple[int, int],
    scale: float,
    angle: float,
) -> tuple[Image.Image, Image.Image]:
    tattoo_rgba = _remove_near_white_background(tattoo_rgba)
    tattoo_rgba = _rotate(tattoo_rgba, angle)

    body_w, body_h = body_rgb.size
    target_width = int(body_w * scale)
    tattoo_rgba = _resize_keep_aspect(tattoo_rgba, target_width)
    tw, th = tattoo_rgba.size

    cx, cy = center_xy
    left = int(cx - tw / 2)
    top = int(cy - th / 2)

    preview = body_rgb.convert("RGBA")
    overlay = Image.new("RGBA", preview.size, (0, 0, 0, 0))
    overlay.paste(tattoo_rgba, (left, top), tattoo_rgba)
    preview = Image.alpha_composite(preview, overlay)

    mask = Image.new("L", preview.size, 0)
    mask_overlay = Image.new("L", preview.size, 0)
    alpha = tattoo_rgba.split()[-1]
    mask_overlay.paste(alpha, (left, top))

    # Slightly dilate + feather the mask so inpainting has room to blend into skin.
    mask = mask_overlay.filter(ImageFilter.MaxFilter(size=9)).filter(ImageFilter.GaussianBlur(radius=5))
    return preview.convert("RGB"), mask


def _fit_to_model_size(img: Image.Image, max_side: int = 512) -> tuple[Image.Image, tuple[int, int]]:
    w, h = img.size
    scale = min(max_side / max(w, h), 1.0)
    new_w = max(64, int(round((w * scale) / 8) * 8))
    new_h = max(64, int(round((h * scale) / 8) * 8))
    resized = img.resize((new_w, new_h), Image.LANCZOS)
    return resized, (w, h)


def get_pipeline(
    model_id: str = DEFAULT_MODEL_ID,
    device: str = "cpu",
) -> StableDiffusionInpaintPipeline:
    key = (model_id, device)
    if key in _PIPELINE_CACHE:
        return _PIPELINE_CACHE[key]

    torch_dtype = torch.float32 if device == "cpu" else torch.float16
    pipe = StableDiffusionInpaintPipeline.from_pretrained(
        model_id,
        torch_dtype=torch_dtype,
    )
    pipe = pipe.to(device)
    pipe.set_progress_bar_config(disable=True)
    if hasattr(pipe, "enable_attention_slicing"):
        pipe.enable_attention_slicing()
    if hasattr(pipe, "enable_vae_slicing"):
        pipe.enable_vae_slicing()

    _PIPELINE_CACHE[key] = pipe
    return pipe


def apply_tattoo(
    body_image: ImageInput,
    tattoo_image: ImageInput,
    position: Tuple[int, int],
    *,
    scale: float = 0.22,
    angle: float = 0.0,
    model_id: str = DEFAULT_MODEL_ID,
    device: str = "cpu",
    resolution: int = 512,
    num_inference_steps: int = 18,
    strength: float = 0.72,
    guidance_scale: float = 7.0,
    prompt: str = DEFAULT_PROMPT,
    negative_prompt: str = DEFAULT_NEGATIVE_PROMPT,
    seed: Optional[int] = 42,
    output_path: Optional[Union[str, Path]] = None,
) -> TattooResult:
    """
    Backend-ready AI tattoo try-on function.

    Parameters
    ----------
    body_image:
        Path or PIL image of the body part photo.
    tattoo_image:
        Path or PIL image of the tattoo design.
    position:
        (x, y) center point on the body image.
    scale:
        Tattoo width as a fraction of the body image width.
    angle:
        Rotation of the tattoo in degrees.
    output_path:
        If provided, saves the final result to this path.
    """
    body_rgb = _load_image(body_image, mode="RGB")
    tattoo_rgba = _load_image(tattoo_image, mode="RGBA")

    preview, mask = _build_preview_and_mask(
        body_rgb=body_rgb,
        tattoo_rgba=tattoo_rgba,
        center_xy=position,
        scale=scale,
        angle=angle,
    )

    preview_small, original_size = _fit_to_model_size(preview, max_side=resolution)
    mask_small = mask.resize(preview_small.size, Image.LANCZOS)

    generator = None
    if seed is not None:
        if device == "cpu":
            generator = torch.Generator().manual_seed(seed)
        else:
            generator = torch.Generator(device=device).manual_seed(seed)

    pipe = get_pipeline(model_id=model_id, device=device)
    result = pipe(
        prompt=prompt,
        negative_prompt=negative_prompt,
        image=preview_small,
        mask_image=mask_small,
        num_inference_steps=num_inference_steps,
        guidance_scale=guidance_scale,
        strength=strength,
        generator=generator,
    )

    generated = result.images[0].resize(original_size, Image.LANCZOS)

    # Preserve everything outside the tattoo area from the original body image.
    feathered_mask = mask.filter(ImageFilter.GaussianBlur(radius=4))
    final_image = Image.composite(generated, body_rgb, feathered_mask)

    if output_path is not None:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        final_image.save(output_path)

    return TattooResult(image=final_image, preview=preview, mask=mask)


if __name__ == "__main__":
    # Example local run.
    result = apply_tattoo(
        body_image="body.png",
        tattoo_image="tattoo.jpg",
        position=(100, 200),
        scale=0.22,
        angle=0,
        output_path="output.png",
    )
    result.preview.save("preview.png")
    result.mask.save("mask.png")
    print("Saved: output.png, preview.png, mask.png")

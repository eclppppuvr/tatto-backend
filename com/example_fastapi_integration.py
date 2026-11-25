from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import FileResponse

from tattoo_ai_service import apply_tattoo

app = FastAPI(title="AI Tattoo Studio Backend Example")

BASE_DIR = Path(__file__).resolve().parent
TMP_DIR = BASE_DIR / "tmp"
TMP_DIR.mkdir(exist_ok=True)


@app.post("/tattoo/try-on")
async def tattoo_try_on(
    body: UploadFile = File(...),
    tattoo: UploadFile = File(...),
    x: int = Form(...),
    y: int = Form(...),
    scale: float = Form(0.22),
    angle: float = Form(0.0),
):
    req_id = uuid4().hex
    body_path = TMP_DIR / f"{req_id}_body_{body.filename}"
    tattoo_path = TMP_DIR / f"{req_id}_tattoo_{tattoo.filename}"
    output_path = TMP_DIR / f"{req_id}_output.png"

    body_path.write_bytes(await body.read())
    tattoo_path.write_bytes(await tattoo.read())

    apply_tattoo(
        body_image=body_path,
        tattoo_image=tattoo_path,
        position=(x, y),
        scale=scale,
        angle=angle,
        output_path=output_path,
    )

    return FileResponse(output_path, media_type="image/png", filename="tattoo_result.png")

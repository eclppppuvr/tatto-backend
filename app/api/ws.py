"""INT-3 (TB-03): WebSocket прогресса. Клиент подключается с ?token=<access_token>.
Ошибки подключения сообщаются кодами закрытия 4401 (токен), 4403 (чужой job), 4404 (нет job):
браузер всё равно не видит HTTP-статус неудачного handshake."""
from __future__ import annotations

import asyncio
import json
from uuid import UUID

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from starlette.concurrency import run_in_threadpool

from ..db.repos import SqlJobRepo
from ..domain.entities import TERMINAL_STATUSES, Job
from ..domain.errors import InvalidAccessToken
from ..security import decode_access_token
from ..services.events import channel_name, job_event

router = APIRouter(prefix="/ws", tags=["ws"])

MAX_STREAM_SECONDS = 15 * 60
RECHECK_SECONDS = 5.0


async def _load(app, job_id: UUID) -> Job | None:
    def work() -> Job | None:
        with app.state.session_factory() as session:
            return SqlJobRepo(session).get(job_id)

    return await run_in_threadpool(work)


@router.websocket("/jobs/{job_id}")
async def job_progress(websocket: WebSocket, job_id: UUID, token: str = Query("")):
    await websocket.accept()
    app = websocket.app
    try:
        claims = decode_access_token(token, app.state.settings.jwt_secret)
    except InvalidAccessToken:
        await websocket.close(code=4401, reason="Токен недействителен")
        return
    job = await _load(app, job_id)
    if job is None:
        await websocket.close(code=4404, reason="Job не найден")
        return
    if job.user_id != claims.user_id:
        await websocket.close(code=4403, reason="Job не принадлежит пользователю")
        return

    try:
        if job.status in TERMINAL_STATUSES:
            await websocket.send_json(job_event(job))
            await websocket.close()
            return
        redis_url = app.state.settings.redis_url
        if not redis_url:
            await websocket.close(code=1011, reason="Канал прогресса не настроен")
            return
        await _stream(websocket, app, job_id, redis_url)
    except (WebSocketDisconnect, RuntimeError):
        return  # клиент ушёл


async def _stream(websocket: WebSocket, app, job_id: UUID, redis_url: str) -> None:
    import redis.asyncio as aioredis

    client = aioredis.from_url(redis_url)
    pubsub = client.pubsub()
    try:
        # Сначала подписка, потом чтение состояния: событие между ними не потеряется.
        await pubsub.subscribe(channel_name(job_id))
        job = await _load(app, job_id)
        if job is None:
            await websocket.close(code=4404, reason="Job не найден")
            return
        await websocket.send_json(job_event(job))
        if job.status in TERMINAL_STATUSES:
            await websocket.close()
            return

        loop = asyncio.get_running_loop()
        deadline = loop.time() + MAX_STREAM_SECONDS
        while loop.time() < deadline:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=RECHECK_SECONDS)
            if message is None:
                # Страховка от потерянных pub/sub-сообщений: сверяемся с БД.
                job = await _load(app, job_id)
                if job is not None and job.status in TERMINAL_STATUSES:
                    await websocket.send_json(job_event(job))
                    await websocket.close()
                    return
                continue
            data = message["data"]
            text = data.decode("utf-8") if isinstance(data, bytes) else str(data)
            await websocket.send_text(text)
            if json.loads(text).get("type") in ("done", "error"):
                await websocket.close()
                return
        await websocket.close(code=1001, reason="Превышено время ожидания")
    finally:
        try:
            await pubsub.unsubscribe()
            await pubsub.aclose()
            await client.aclose()
        except Exception:  # noqa: BLE001 — закрытие best effort
            pass

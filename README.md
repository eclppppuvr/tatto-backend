# tatto-backend

Бэкенд AI Tattoo Studio (эпик TBACK-001). Спецификации — в `coddoc/TBACK-001/`.

## Статус

| Часть | Состояние |
|-------|-----------|
| TB-02 Личный кабинет (INT-1…INT-7) | реализовано: `app/` |
| Фундамент задач: `jobs`, `GET /v1/jobs/{id}`, `WS /v1/ws/jobs/{id}`, Celery (очереди `cpu`/`gpu`), S3, `AIEngine` | реализовано, движок пока `stub` |
| TB-03 Extract, TB-04 Generation, TB-05 Try-On | не начато (обработчики, MongoDB, `/v1/sketches/*`, `/v1/generation`, `/v1/tryon`) |

`com/` — наработки команды, в сервис не подключается (в `.gitignore`).

## Запуск

```bash
cp .env.example .env            # заполнить JWT_SECRET
docker compose up --build       # PostgreSQL + API на :8000, миграции применяются при старте
```

Документация API: http://localhost:8000/docs
MinIO-консоль: http://localhost:9001 (логин/пароль из `S3_ACCESS_KEY`/`S3_SECRET_KEY`, по умолчанию `tattoo` / `tattoo-secret-123`).

Воркер запускается отдельным контейнером `worker-cpu`. Локально без Docker:
`celery -A app.worker.main:celery worker -Q cpu -l info`.

## Разработка и тесты

```bash
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest                 # или: python -m unittest discover -s tests -t .
```

Без БД работают тесты бизнес-логики (`tests/test_*service.py`, `test_security.py`, `test_rate_limit.py`);
`tests/test_api.py` использует SQLite in-memory.

## Структура

- `app/domain` — сущности, порты (интерфейсы хранилищ), ошибки
- `app/services` — бизнес-логика (без FastAPI и ORM)
- `app/db` — модели и репозитории SQLAlchemy
- `app/api` — HTTP-слой (REST и WebSocket)
- `app/worker` — Celery: приложение, диспетчер, реестр обработчиков (`handlers.py`), точка входа воркера
- `app/ai` — интерфейс `AIEngine`, `stub`, реестр по `AI_ENGINE`
- `app/storage.py` — S3/MinIO (ключи иммутабельны)
- `migrations/` — Alembic: users, profiles, refresh_tokens, jobs

## Как добавить обработчик задачи

1. Реализовать функцию `handler(ctx: JobContext) -> output_ref` (прогресс — `ctx.report(0..99)`).
   Временный сбой — `raise TransientJobError()` (повтор через 10/30/90 с, максимум 3 раза);
   окончательный отказ — `raise JobFailure(message, code)`.
2. Зарегистрировать её в `app/worker/handlers.py` по `JobType`.
3. В API создать задачу через `JobService.submit(...)`: он коммитит транзакцию и только потом ставит задачу в очередь.

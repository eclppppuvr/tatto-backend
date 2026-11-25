# tatto-backend

Бэкенд AI Tattoo Studio (эпик TBACK-001). Спецификации — в `coddoc/TBACK-001/`.

## Статус

| Часть | Состояние |
|-------|-----------|
| TB-02 Личный кабинет (INT-1…INT-7) | реализовано: `app/` |
| TB-03 Extract, TB-04 Generation, TB-05 Try-On | не начато (общие `jobs`, Celery, S3, MongoDB) |

`com/` — наработки команды, в сервис не подключается (в `.gitignore`).

## Запуск

```bash
cp .env.example .env            # заполнить JWT_SECRET
docker compose up --build       # PostgreSQL + API на :8000, миграции применяются при старте
```

Документация API: http://localhost:8000/docs

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
- `app/api` — HTTP-слой
- `migrations/` — Alembic, три миграции по ТЗ (users, profiles, refresh_tokens)

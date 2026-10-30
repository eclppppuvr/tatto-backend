# Техническая спецификация: Считывание эскиза с фото (Extract)

> **Задача:** TB-03
> **Автор:** —
> **Источник (БТ):** coddoc/TBACK-001/TB-03/business_requirements.md
> **Редакция:** 1 (2026-10-31): первая запись
> **Версия скилла:** technical-spec-doc 1.8.0
>
> **Статус готовности:** Готово к разработке
>
> **Открытые вопросы (решить до / во время разработки):**
> — Все технические решения приняты, спецификация готова к разработке.

**Легенда происхождения:**
🟢 НОВОЕ — спроектировано в этом документе, реализуется как есть.
🔵 подтверждено аналитиком — факт о существующей системе; источник указан у пункта; валидировать при интеграции.
🟡 к валидации — допущение о существующей системе, не подтверждено — уточнить.
❓ — открытое архитектурное решение.
⚠️ — подтверждено, но расплывчато: требует уточнения перед разработкой.

## 1. Обзор изменения

### 1.1. Что делаем и тип изменения
**Суть:** Пользователь загружает фотографию татуировки на теле через multipart-загрузку. Система асинхронно обрабатывает изображение через AI-пайплайн (stub на MVP): извлекает контур татуировки, удаляет фон, дорисовывает недостающие элементы, переводит на белый фон. Результат — готовый эскиз в MongoDB, исходник — в S3. Пользователь видит прогресс через WebSocket с fallback на polling.

**Тип:** новый функционал
**Стороны:** Fullstack

### 1.2. Затронутые сервисы и владельцы

| Сервис | Роль в задаче | Владелец/команда | Происхождение |
|--------|---------------|------------------|---------------|
| API (tatto-backend) | Новый сервис, владелец всех взаимодействий | Команда проекта | 🟢 |
| Celery worker | Асинхронная обработка AI-пайплайна | Команда проекта | 🟢 |
| S3 (MinIO) | Хранение исходных и результирующих изображений | Команда проекта | 🟢 |
| PostgreSQL | Хранение Jobs (статус, прогресс) | Команда проекта | 🟢 |
| MongoDB | Хранение эскизов (sketches) | Команда проекта | 🟢 |
| Redis | Broker для Celery, pub/sub для WebSocket | Команда проекта | 🟢 |

### 1.3. Связь с бизнес-требованиями
Реализует FR-1 из БТ: пользователь загружает фото татуировки на теле, получает готовый эскиз на белом фоне с точностью извлечения не менее 70%.

## 2. Взаимодействия (ядро)

### INT-1. Загрузка фото и запуск extract — 🟢
- **Вид:** новое
- **Граница/направление:** FE → BE
- **Триггер:** пользователь выбирает фото и нажимает «Извлечь эскиз»
- **Контракт (запрос):** `POST /v1/sketches/extract`
  - multipart/form-data
  - `file` (file, required) — изображение (JPEG/PNG, max 10 MB)
  - `title` (string, optional, max 100) — название эскиза
- **Контракт (ответ):** `202 Accepted`
  - `job_id` (UUID) — ID задачи
  - `status` (enum: `pending`) — начальный статус
- **Пример запроса:**
  ```
  ------form boundary
  Content-Disposition: form-data; name="file"; filename="tattoo.jpg"
  Content-Type: image/jpeg
  
  [binary data]
  ------form boundary
  Content-Disposition: form-data; name="title"
  
  Моя тату
  ------form boundary--
  ```
- **Пример ответа (успех):**
  ```json
  {
    "job_id": "j1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "status": "pending"
  }
  ```
- **Ошибки:**
  - `400 Bad Request` — «Файл не загружен»
  - `415 Unsupported Media Type` — «Неподдерживаемый формат (только JPEG/PNG)»
  - `413 Payload Too Large` — «Файл превышает 10 MB»
  - `401 Unauthorized` — «Неавторизован»
  - `422 Unprocessable` — «Некорректное имя файла»
- **Состояния UI по ответу:** значение → показать job_id, переключиться на экран прогресса; ошибка → показать сообщение
- **Авторизация:** JWT required
- **Происхождение:** 🟢 новое
- **Трассировка:** FR-1

### INT-2. Получение статуса Job — 🟢
- **Вид:** новое
- **Граница/направление:** FE → BE
- **Триггер:** polling (каждые 5 сек) или WebSocket disconnect
- **Контракт (запрос):** `GET /v1/jobs/{job_id}`
  - Authorization: `Bearer <access_token>`
- **Контракт (ответ):** `200 OK`
  - `id` (UUID)
  - `status` (enum: `pending`, `running`, `done`, `failed`, `cancelled`)
  - `progress` (integer, 0–100) — текущий прогресс
  - `output_ref` (string | null) — S3-ключ или MongoDB _id результата
  - `error_code` (string | null) — машинный код ошибки
  - `error_message` (string | null) — человекочитаемое описание ошибки
  - `created_at` (ISO 8601)
  - `finished_at` (ISO 8601 | null)
- **Пример ответа (running):**
  ```json
  {
    "id": "j1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "status": "running",
    "progress": 45,
    "output_ref": null,
    "error_code": null,
    "error_message": null,
    "created_at": "2026-10-31T10:00:00Z",
    "finished_at": null
  }
  ```
- **Пример ответа (done):**
  ```json
  {
    "id": "j1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "status": "done",
    "progress": 100,
    "output_ref": "sk_a1b2c3d4e5f6",
    "error_code": null,
    "error_message": null,
    "created_at": "2026-10-31T10:00:00Z",
    "finished_at": "2026-10-31T10:01:30Z"
  }
  ```
- **Пример ответа (failed):**
  ```json
  {
    "id": "j1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "status": "failed",
    "progress": 30,
    "output_ref": null,
    "error_code": "model_timeout",
    "error_message": "AI-модель не ответила в течение 120 секунд",
    "created_at": "2026-10-31T10:00:00Z",
    "finished_at": "2026-10-31T10:02:00Z"
  }
  ```
- **Ошибки:**
  - `401 Unauthorized` — «Токен недействителен»
  - `403 Forbidden` — «Job не принадлежит пользователю»
  - `404 Not Found` — «Job не найден»
- **Состояния UI по ответу:** `pending` → спиннер; `running` → прогресс-бар; `done` → показать результат; `failed` → показать ошибку + кнопку «Повторить»
- **Авторизация:** JWT required
- **Происхождение:** 🟢 новое
- **Трассировка:** FR-1

### INT-3. WebSocket: получение прогресса — 🟢
- **Вид:** новое
- **Граница/направление:** FE ↔ BE
- **Триггер:** подключение клиента к WebSocket-каналу
- **Контракт (подключение):** `WS /v1/ws/jobs/{job_id}`
  - Подключается с JWT в query-параметре: `?token=<access_token>`
- **Контракт (сообщение от сервера):** JSON, отправляется при каждом изменении статуса Job
  - `type` (enum: `progress`, `done`, `error`)
  - `job_id` (UUID)
  - `progress` (integer, 0–100) — текущий прогресс
  - `status` (enum: `pending`, `running`, `done`, `failed`)
  - `message` (string | null) — сообщение об ошибке (при type=error)
- **Пример сообщения (progress):**
  ```json
  {
    "type": "progress",
    "job_id": "j1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "progress": 60,
    "status": "running",
    "message": null
  }
  ```
- **Пример сообщения (done):**
  ```json
  {
    "type": "done",
    "job_id": "j1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "progress": 100,
    "status": "done",
    "message": null
  }
  ```
- **Пример сообщения (error):**
  ```json
  {
    "type": "error",
    "job_id": "j1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "progress": 30,
    "status": "failed",
    "message": "AI-модель не ответила в течение 120 секунд"
  }
  ```
- **Ошибки подключения:**
  - `401 Unauthorized` — токен недействителен (WS-соединение разрывается)
  - `404 Not Found` — job не найден
- **Состояния UI по ответу:** `progress` → обновить прогресс-бар; `done` → показать результат; `error` → показать ошибку
- **Авторизация:** JWT в query-параметре
- **Происхождение:** 🟢 новое
- **Трассировка:** FR-1

### INT-4. Получение результата extract — 🟢
- **Вид:** новое
- **Граница/направление:** FE → BE
- **Триггер:** пользователь открывает результат extract
- **Контракт (запрос):** `GET /v1/sketches/{sketch_id}`
  - Authorization: `Bearer <access_token>`
- **Контракт (ответ):** `200 OK`
  - `id` (string, MongoDB ObjectId)
  - `user_id` (UUID)
  - `source` (enum: `extract`)
  - `title` (string | null)
  - `status` (enum: `active`, `deleted`)
  - `s3` (object) — `result_png` (S3-ключ), `thumbnail` (S3-ключ)
  - `meta` (object) — `width` (int), `height` (int), `model` (string), `latency_ms` (int)
  - `created_at` (ISO 8601)
- **Пример ответа (успех):**
  ```json
  {
    "id": "sk_a1b2c3d4e5f6",
    "user_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "source": "extract",
    "title": "Моя тату",
    "status": "active",
    "s3": {
      "result_png": "sketches/sk_a1b2c3d4e5f6.png",
      "thumbnail": "sketches/sk_a1b2c3d4e5f6_thumb.jpg"
    },
    "meta": {
      "width": 1024,
      "height": 1024,
      "model": "stub-extractor",
      "latency_ms": 45000
    },
    "created_at": "2026-10-31T10:01:30Z"
  }
  ```
- **Ошибки:**
  - `401 Unauthorized` — «Токен недействителен»
  - `403 Forbidden` — «Эскиз не принадлежит пользователю»
  - `404 Not Found` — «Эскиз не найден или удалён»
- **Состояния UI по ответу:** значение → показать эскиз; ошибка → «Эскиз не найден»
- **Авторизация:** JWT required
- **Происхождение:** 🟢 новое
- **Трассировка:** FR-1

### Каталог ошибок (сводно)

| Код | Тело/сообщение | Когда | Состояние UI |
|-----|----------------|-------|--------------|
| 400 | «Некорректный запрос» | Файл не загружен / формат неверный | Показать ошибку валидации |
| 401 | «Неавторизован» | Токен недействителен | Редирект на логин |
| 403 | «Доступ запрещён» | Job/эскиз не принадлежит пользователю | Показать «нет доступа» |
| 404 | «Не найдено» | Job/эскиз не существует | Показать «не найдено» |
| 413 | «Файл слишком большой» | Файл > 10 MB | Показать «максимум 10 MB» |
| 415 | «Неподдерживаемый формат» | Только JPEG/PNG | Показать «только JPEG/PNG» |
| 422 | «Ошибка валидации» | Некорректные поля | Подсветить поля |
| 500 | «Внутренняя ошибка сервера» | Неожиданная ошибка | «Сервис временно недоступен» |
| 504 | «Таймаут обработки» | AI-модель > 120 сек | Показать ошибку + «Повторить» |

## 3. Backend — ответственность

### 3.1. По сервисам

**API (tatto-backend)** — реализует INT-1, INT-2, INT-4.

- INT-1 (extract upload): валидация файла (формат, размер), сохранение в S3 (`raw/{uuid}.jpg`), создание Job в PostgreSQL со статусом `pending`, публикация события в Redis для Celery, возврат `job_id`
- INT-2 (job status): чтение Job из PostgreSQL, проверка ownership (user_id из JWT)
- INT-4 (sketch detail): чтение эскиза из MongoDB, проверка ownership

**Celery worker** — обработка AI-пайплайна.

- Подписка на очередь `cpu` (Celery + Redis broker)
- Забирает задачу из очереди, обновляет Job на `running`, публикует прогресс в Redis pub/sub (`job:channel:{job_id}`)
- Вызывает AIEngine.extract_sketch() (stub на MVP)
- Сохраняет результат в S3 (`sketches/{uuid}.png`), создаёт документ в MongoDB (sketches)
- Обновляет Job на `done` (или `failed` при ошибке), публикует финальный прогресс (100 или error)

**S3 (MinIO)** — хранение изображений.

- Bucket `tattoo`
- Префиксы: `raw/` (исходники), `sketches/` (результаты)
- Ключи иммутабельны (никогда не перезаписываются)

**PostgreSQL** — хранение Jobs.

- Таблица `jobs`: `id` (UUID, PK), `user_id` (UUID, FK), `type` (ENUM: `extract_sketch`, `generate_design`, `try_on`), `status` (ENUM: `pending`, `running`, `done`, `failed`, `cancelled`), `progress` (SMALLINT, 0–100), `input_ref` (TEXT, S3-ключ), `output_ref` (TEXT, S3-ключ или MongoDB _id), `error_code` (VARCHAR 50), `error_message` (TEXT), `retry_count` (SMALLINT), `created_at`, `updated_at`, `started_at`, `finished_at`

**MongoDB** — хранение эскизов.

- Коллекция `sketches`: `_id` (ObjectId), `user_id` (UUID), `source` (ENUM: `extract`, `generation`), `title`, `status` (ENUM: `active`, `deleted`), `s3` (object: `result_png`, `thumbnail`), `meta` (object: `width`, `height`, `model`, `latency_ms`), `created_at`

**Redis** — broker + pub/sub.

- Broker для Celery: `redis://:password@localhost:6379/0`
- Pub/sub каналы: `job:channel:{job_id}` — при каждом изменении статуса воркер публикует сообщение `{type, job_id, progress, status}`
- TTL для каналов: нет (эфемерные)

### 3.2. Данные и хранение

- 🟢 `jobs` (PostgreSQL) — таблица: `id` (UUID, PK), `user_id` (UUID, FK → users.id ON DELETE CASCADE), `type` (ENUM: `extract_sketch`, `generate_design`, `try_on`), `status` (ENUM: `pending`, `running`, `done`, `failed`, `cancelled`, default `pending`), `progress` (SMALLINT, 0–100, default 0), `input_ref` (TEXT, S3-ключ), `output_ref` (TEXT, S3-ключ или MongoDB _id), `error_code` (VARCHAR 50, nullable), `error_message` (TEXT, nullable), `retry_count` (SMALLINT, default 0), `created_at` (TIMESTAMPTZ), `updated_at` (TIMESTAMPTZ), `started_at` (TIMESTAMPTZ, nullable), `finished_at` (TIMESTAMPTZ, nullable)
- 🟢 `sketches` (MongoDB) — коллекция: `_id` (ObjectId, PK), `user_id` (UUID), `source` (ENUM: `extract`, `generation`), `title` (string, nullable), `status` (ENUM: `active`, `deleted`, default `active`), `s3` (object: `result_png` string, `thumbnail` string), `meta` (object: `width` int, `height` int, `model` string, `latency_ms` int), `created_at` (ISODate)
- Индексы PostgreSQL: `(user_id, created_at DESC)`, `(status) WHERE status IN ('pending', 'running')`, `(type, status)`
- Индексы MongoDB: `{user_id: 1, created_at: -1}`, `{user_id: 1, source: 1}`, `{tags: 1}`
- Миграции PostgreSQL: 1 DDL-миграция (добавление type `extract_sketch` в enum job_type, если ещё не добавлен)

### 3.3. Авторизация/доступ на бэке

- INT-1, INT-2, INT-4 требуют JWT в заголовке `Authorization: Bearer <token>`
- Валидация: проверка подписи JWT, срока действия
- INT-2, INT-4: проверка ownership (user_id из JWT совпадает с user_id Job/эскиза)
- INT-3 (WebSocket): JWT в query-параметре, проверка подписи

## 4. Frontend — ответственность

### 4.1. Где и что меняется в UI

- Экран загрузки: кнопка «Загрузить фото», drag-and-drop зона, валидация формата/размера
- Экран прогресса: job_id, прогресс-бар (0–100%), статус обработки
- Экран результата: превью эскиза (S3-ключ → presigned URL), кнопка «Скачать», кнопка «Примерить» (переход к Try-On)

### 4.2. Пользовательские сценарии

**Основной поток (FR-1):**
1. Пользователь открывает экран «Извлечь эскиз»
2. Загружает фото (drag-and-drop или выбор файла) → INT-1
3. Получает job_id → переключается на экран прогресса
4. Подключается к WebSocket `job:channel:{job_id}` → получает прогресс в реальном времени
5. При `status=done` → получает sketch_id → INT-4 → показывает результат

**Ветвление (polling fallback):**
1. WebSocket подключение не удалось (или разорвалось)
2. Фронт опрашивает `GET /v1/jobs/{job_id}` каждые 5 секунд → INT-2
3. При `status=done` → INT-4 → показывает результат

**Ветвление (ошибка обработки):**
1. AI-обработка завершилась ошибкой
2. WS отправляет `type=error` или polling возвращает `status=failed`
3. Фронт показывает ошибку + кнопку «Повторить» (INT-1 с тем же файлом)

### 4.3. Состояния (именованные)

| Имя состояния | Условие | Что видит пользователь |
|---------------|---------|------------------------|
| `idle` | До загрузки | Форма загрузки, drag-and-drop зона |
| `uploading` | Отправка multipart | Спиннер «Загрузка...» |
| `pending` | Job создан, обработка не началась | «Задача в очереди...» |
| `processing` | Job running, progress < 100 | Прогресс-бар с процентом |
| `done` | Job done, status=done | Превью эскиза, кнопки «Скачать», «Примерить» |
| `error` | Job failed, status=failed | Сообщение об ошибке + кнопка «Повторить» |
| `error_network` | WS disconnect + polling не отвечает | «Соединение потеряно» + кнопка «Повторить» |

### 4.3.1. Loading и таймауты

- **Таймаут загрузки файла:** 30 секунд
- **Таймаут polling:** 10 секунд
- **Polling интервал:** 5 секунд (если WS недоступен)
- **Hard-limit AI-обработки:** 120 секунд (согласно БТ)
- При таймауте → состояние `error_network` + кнопка «Повторить»

### 4.4. Доступ по ролям в UI

- `client`, `master`: полный доступ к extract
- `admin`: полный доступ

## 5. Нефункциональные требования

### 5.1. Синхронность, кэш, производительность

- INT-1: синхронный ответ (202 Accepted), обработка асинхронная
- INT-2: синхронный запрос к PostgreSQL
- INT-3: WebSocket, Redis pub/sub (эфемерные, без TTL)
- AI-пайплайн (stub): ~5 секунд на MVP (в будущем — до 120 секунд для реальных моделей)
- Очередь Celery: `cpu` (для extract и generation), `gpu` (для try-on, в будущих задачах)
- Retry: max 3 попытки, exponential backoff (10s, 30s, 90s)

### 5.2. Надёжность/деградация

- При недоступности S3: API возвращает 503, фронт показывает «хранилище временно недоступен»
- При недоступности Redis: Celery не может забирать задачи, API продолжает принимать загрузки (jobs остаются `pending`)
- При недоступности MongoDB: результат сохраняется в S3, но MongoDB не обновляется — ошибка логируется, job помечается `failed`
- Job при `failed` с `retry_count < 3` автоматически перезапускается воркером

### 5.3. Безопасность/доступ (сводно)

- JWT-авторизация на всех эндпоинтах кроме INT-1 (multipart)
- Валидация файлов: только JPEG/PNG, max 10 MB, проверка magic bytes
- S3-ключи иммутабельны: никогда не перезаписываются, только создание новых
- Ownership-проверка на INT-2, INT-4: user_id из JWT vs user_id в БД

## 6. Релиз и интеграция

### 6.1. Порядок выката

1. BE: миграции БД (jobs, sketches), API-эндпоинты (INT-1, INT-2, INT-4)
2. Workers: Celery-воркер с AIEngine stub
3. FE: интеграция с новыми эндпоинтами + WebSocket

BE и workers деплоятся одновременно, FE — после.

### 6.2. Обратная совместимость

- На данном этапе нет существующих потребителей — обратная совместимость не применима
- Все эндпоинты версионируются (`/v1/...`)

### 6.3. Фиче-флаги

Не применимо: задача не использует фиче-флаги

### 6.4. План отката

- **Откат только BE:** API перестаёт создавать jobs, старые jobs остаются в `pending`/`running`. FE на старой версии не вызывает новые эндпоинты — безопасно.
- **Откат только FE:** BE отдаёт новые эндпоинты, FE игнорирует — безопасно.
- **Откат workers:** jobs остаются `running` indefinitely — FE показывает прогресс-бар, но не получает финальный статус.

### 6.5. Преднастройка до релиза (чек-лист)

- [ ] Роли в security-сервисе — роли `client`, `master`, `admin` (из TB-02)
- [ ] DDL-миграция в репо владеющего сервиса — jobs (type enum), sketches (MongoDB schema)
- [ ] Конфиги по окружениям (dev/staging/prod) — S3_URL, REDIS_URL, CELERY_BROKER_URL, AI_ENGINE=stub
- [ ] Сервисные аккаунты для межсервисных вызовов — не требуется (MVP, один сервис)
- [x] Фиче-флаги заведены — не требуются

## 7. Трассировка приёмки

| FR из БТ | Взаимодействие(я) | Тест-кейс (Дано–Когда–Тогда) |
|----------|-------------------|-------------------------------|
| FR-1 | INT-1, INT-3, INT-4 | Дано пользователь авторизован и имеет фото татуировки, когда он загружает фото, тогда система создаёт Job и возвращает job_id |
| FR-1 | INT-2, INT-3 | Дано Job создан со статусом pending, когда обработка завершена, тогда пользователь видит статус done и результат |
| FR-1 | INT-4 | Дано Job завершён успешно, когда пользователь открывает результат, тогда он видит эскиз на белом фоне |
| FR-1 | INT-2 | Дано обработка завершилась ошибкой, когда пользователь опрашивает статус, тогда он получает status=failed с error_code |

## 8. Допущения и открытые вопросы

- 🔵 Подтверждено аналитиком: multipart через бэк; Celery + Redis; WebSocket + polling fallback; AIEngine stub на MVP; задача TB-03.
- 🟡 К валидации: —
- ❓ Открытые решения: —
- ⚠️ Требует уточнения: —
- Технические риски: AI-пайплайн (stub → реальные модели) — замена через env-флаг `AI_ENGINE=stub|real`
- Унаследовано из БТ (бизнес-пробелы): —
- Приложений из БТ: критерий точности извлечения ≥ 70% (по субъективной оценке пользователей)

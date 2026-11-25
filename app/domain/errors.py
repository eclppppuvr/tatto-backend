"""Прикладные ошибки. Тексты и коды — из каталога ошибок TB-02."""


class AppError(Exception):
    status_code = 500
    message = "Внутренняя ошибка сервера"

    def __init__(self, message: str | None = None):
        super().__init__(message or self.message)
        self.message = message or self.message


class EmailTaken(AppError):
    status_code = 409
    message = "Пользователь с таким email уже существует"


class InvalidCredentials(AppError):
    status_code = 401
    message = "Неверный email или пароль"


class AccountBlocked(AppError):
    status_code = 403
    message = "Аккаунт заблокирован"


class InvalidRefreshToken(AppError):
    status_code = 401
    message = "Refresh-токен недействителен или истёк"


class RevokedRefreshToken(AppError):
    status_code = 401
    message = "Токен отозван"


class InvalidAccessToken(AppError):
    status_code = 401
    message = "Токен недействителен"


class UserNotFound(AppError):
    status_code = 404
    message = "Пользователь не найден"


class TooManyAttempts(AppError):
    # В спеке указана только блокировка на 15 минут, код не задан — берём 429.
    status_code = 429
    message = "Слишком много неудачных попыток входа. Повторите позже"


class JobNotFound(AppError):
    status_code = 404
    message = "Job не найден"


class JobForbidden(AppError):
    status_code = 403
    message = "Job не принадлежит пользователю"


class StorageUnavailable(AppError):
    status_code = 503
    message = "Хранилище временно недоступно"


# --- Ошибки обработки задач (не HTTP): их разбирает JobRunner ---

class JobFailure(Exception):
    """Окончательная ошибка обработки: job -> failed, без повторов."""

    code = "job_failed"
    message = "Не удалось обработать задачу"

    def __init__(self, message: str | None = None, code: str | None = None):
        super().__init__(message or self.message)
        self.message = message or self.message
        self.code = code or self.code


class TransientJobError(JobFailure):
    """Временный сбой (сеть, перегрузка модели): воркер повторит задачу с backoff."""

    code = "transient_error"
    message = "Временная ошибка обработки"


class JobTimeout(JobFailure):
    code = "model_timeout"
    message = "AI-модель не ответила в течение 120 секунд"

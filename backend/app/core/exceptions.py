"""애플리케이션 도메인 예외.

Service는 HTTP를 모른다. 대신 이 예외들을 던지고, main.py의 핸들러가
06_API.md의 상태코드·ErrorResponse 형식으로 변환한다(계층 분리).
"""


class AppError(Exception):
    """앱 공통 예외. status_code + code + 메시지를 담는다."""

    status_code: int = 500
    code: str = "INTERNAL_ERROR"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        if code:
            self.code = code


class NotFoundError(AppError):
    status_code = 404
    code = "NOT_FOUND"


class ValidationError(AppError):
    status_code = 400
    code = "VALIDATION_ERROR"


class ConflictError(AppError):
    status_code = 409
    code = "CONFLICT"

class AppError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def to_error_response(exc: Exception, *, debug: bool = False) -> dict:
    """Convert exceptions into an HTTP-like response payload."""
    if isinstance(exc, AppError):
        return {"status_code": exc.status_code, "body": {"error": str(exc)}}
    return {"status_code": 500, "body": {"error": str(exc)}}

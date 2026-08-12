class DomainError(Exception):
    def __init__(self, message: str, *, code: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code


class NotFoundError(DomainError):
    def __init__(self, message: str, *, code: str = "NOT_FOUND"):
        super().__init__(message, code=code, status_code=404)


class ValidationError(DomainError):
    def __init__(self, message: str, *, code: str = "VALIDATION_ERROR"):
        super().__init__(message, code=code, status_code=422)

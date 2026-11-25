class DomainError(Exception):
    def __init__(self, code: str, message: str, details: dict | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


class JudgeOutputError(Exception):
    """The model reply was not the requested schema after the extra retry."""

    def __init__(self, content: object) -> None:
        super().__init__("judge output invalid")
        self.content = content

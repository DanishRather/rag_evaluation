from app.security.crypto import encrypt


def seal(value: str) -> tuple[str, str]:
    return encrypt(value)

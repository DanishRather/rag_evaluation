import re

_PATTERNS = (
    re.compile(r"(?i)(authorization\s*[:=]\s*)(\S+)"),
    re.compile(r"(?i)(bearer\s+)(\S+)"),
    re.compile(r"(?i)(api[_-]?key\s*[:=]\s*[\"']?)([^\"'\s]+)"),
)


def redact(text: str, secret: str | None = None) -> str:
    if not text:
        return text
    cleaned = text
    if secret:
        cleaned = cleaned.replace(secret, "[redacted]")
    for pattern in _PATTERNS:
        cleaned = pattern.sub(r"\1[redacted]", cleaned)
    return cleaned

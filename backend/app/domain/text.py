"""Platform tokenizer. Unicode casefold, whitespace split, edge punctuation stripped."""

import re

_EDGE = re.compile(r"^\W+|\W+$", re.UNICODE)


def tokenize(text: str) -> list[str]:
    if not text:
        return []
    tokens: list[str] = []
    for raw in text.casefold().split():
        token = _EDGE.sub("", raw)
        if token:
            tokens.append(token)
    return tokens


def token_set(text: str) -> set[str]:
    return set(tokenize(text))


def jaccard(left: str, right: str) -> float:
    first, second = token_set(left), token_set(right)
    union = first | second
    if not union:
        return 0.0
    return len(first & second) / len(union)


def coverage(gold: str, chunk: str) -> float:
    gold_tokens = token_set(gold)
    if not gold_tokens:
        return 0.0
    return len(gold_tokens & token_set(chunk)) / len(gold_tokens)


def purity(gold: str, chunk: str) -> float:
    chunk_tokens = token_set(chunk)
    if not chunk_tokens:
        return 0.0
    return len(token_set(gold) & chunk_tokens) / len(chunk_tokens)

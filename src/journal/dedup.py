import hashlib
import html
import re

from selectolax.parser import HTMLParser

_WHITESPACE_RE = re.compile(r"\s+")


def normalize_body(text: str) -> str:
    """Strip HTML tags, decode entities, collapse whitespace, trim."""
    if not text:
        return ""
    # selectolax handles partial-document HTML gracefully.
    plain = HTMLParser(text).text(separator=" ")
    plain = html.unescape(plain)
    plain = _WHITESPACE_RE.sub(" ", plain).strip()
    return plain


def body_hash(text: str) -> str:
    """SHA-256 of UTF-8 encoded text, prefixed with `sha256:`."""
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def dedup_count(hashes: list[str]) -> int:
    """Number of distinct hashes."""
    return len(set(hashes))

"""Bounded, pure Gmail MIME extraction; no fetches, attachments or intent decisions."""

from __future__ import annotations

import base64
import binascii
import codecs
import re
from dataclasses import dataclass
from email.message import Message
from html.parser import HTMLParser
from typing import Any

MAX_DEPTH = 8
MAX_PARTS = 64
MAX_DECODED_BYTES = 128 * 1024
MAX_TEXT_CHARS = 24_000
_CHARSETS = {
    "utf-8", "ascii", "iso8859-1", "iso8859-2", "iso8859-15", "cp1250", "cp1252",
    "utf-16", "utf-16-le", "utf-16-be",
}


class _Refuse(ValueError):
    def __init__(self, status: str, code: str):
        self.status, self.code = status, code


@dataclass
class _Leaf:
    part: dict
    format: str
    charset: str


class _Selection:
    def __init__(self):
        self.parts = 0
        self.unsupported = False

    def select(self, part: Any, depth: int = 0) -> list[_Leaf]:
        self.parts += 1
        if depth > MAX_DEPTH or self.parts > MAX_PARTS:
            raise _Refuse("oversize", "GMAIL_BODY_STRUCTURE_LIMIT")
        if not isinstance(part, dict):
            raise _Refuse("unsupported", "GMAIL_BODY_MALFORMED")
        mime = part.get("mimeType", "")
        if not isinstance(mime, str):
            raise _Refuse("unsupported", "GMAIL_BODY_MALFORMED")
        mime = mime.lower().strip()
        filename = part.get("filename", "")
        if not isinstance(filename, str):
            raise _Refuse("unsupported", "GMAIL_BODY_FILENAME")
        if filename or mime == "message/rfc822":
            return []
        headers = _headers(part)
        disposition = headers.get_content_disposition()
        if disposition == "attachment" or headers.get_filename():
            return []
        if disposition not in {None, "inline"}:
            raise _Refuse("unsupported", "GMAIL_BODY_DISPOSITION")
        if "Content-Type" in headers and headers.get_content_type() != mime:
            raise _Refuse("unsupported", "GMAIL_BODY_CONTENT_TYPE")
        children = part.get("parts", [])
        if not isinstance(children, list):
            raise _Refuse("unsupported", "GMAIL_BODY_MALFORMED")
        if mime.startswith("multipart/"):
            if not children:
                return []
            selections = [self.select(child, depth + 1) for child in children]
            if mime == "multipart/alternative":
                for preferred in ("plain", "html"):
                    choices = [items for items in selections if items and all(
                        leaf.format == preferred for leaf in items
                    )]
                    if len(choices) > 1:
                        raise _Refuse("unsupported", "GMAIL_BODY_AMBIGUOUS_ALTERNATIVE")
                    if choices:
                        return choices[0]
                return []
            if mime == "multipart/related":
                start = headers.get_param("start", header="content-type")
                if start is None:
                    return selections[0]
                indices = [index for index, child in enumerate(children)
                           if _headers(child).get("Content-ID") == start]
                if len(indices) != 1:
                    raise _Refuse("unsupported", "GMAIL_BODY_RELATED_ROOT")
                return selections[indices[0]]
            if mime == "multipart/mixed":
                return [leaf for items in selections for leaf in items]
            raise _Refuse("unsupported", "GMAIL_BODY_MULTIPART_TYPE")
        if children:
            raise _Refuse("unsupported", "GMAIL_BODY_MALFORMED")
        if mime not in {"text/plain", "text/html"}:
            if mime.startswith(("text/", "message/")):
                raise _Refuse("unsupported", "GMAIL_BODY_TEXT_TYPE")
            self.unsupported = self.unsupported or bool(mime)
            return []
        charset = headers.get_content_charset() or "utf-8"
        return [_Leaf(part, "plain" if mime == "text/plain" else "html", charset)]


def _headers(part: dict) -> Message:
    raw = part.get("headers", [])
    if not isinstance(raw, list) or len(raw) > 100:
        raise _Refuse("unsupported", "GMAIL_BODY_HEADERS")
    parsed = Message()
    for header in raw:
        if (not isinstance(header, dict) or not isinstance(header.get("name"), str)
                or not isinstance(header.get("value"), str)):
            raise _Refuse("unsupported", "GMAIL_BODY_HEADERS")
        name, value = header["name"], header["value"]
        if len(name) > 100 or len(value) > 4096:
            raise _Refuse("oversize", "GMAIL_BODY_HEADER_LIMIT")
        if name.lower() not in {"content-type", "content-disposition", "content-id"}:
            continue
        if name in parsed or "\x00" in value:
            raise _Refuse("unsupported", "GMAIL_BODY_HEADERS")
        parsed[name] = value
    for header in ("Content-Type", "Content-Disposition"):
        parameters = parsed.get_params(header=header) or []
        names = [name.lower() for name, _ in parameters[1:]]
        if len(names) != len(set(names)):
            raise _Refuse("unsupported", "GMAIL_BODY_HEADERS")
    return parsed


def _decode(leaf: _Leaf, remaining: int) -> tuple[str, int]:
    body = leaf.part.get("body")
    if not isinstance(body, dict):
        raise _Refuse("unavailable", "GMAIL_BODY_DATA_UNAVAILABLE")
    if body.get("attachmentId"):
        raise _Refuse("unavailable", "GMAIL_BODY_ATTACHMENT_REQUIRED")
    data = body.get("data")
    if not isinstance(data, str):
        raise _Refuse("unavailable", "GMAIL_BODY_DATA_UNAVAILABLE")
    if len(data) > ((remaining + 2) // 3) * 4:
        raise _Refuse("oversize", "GMAIL_BODY_BYTE_LIMIT")
    if not re.fullmatch(r"[A-Za-z0-9_-]*={0,2}", data):
        raise _Refuse("unsupported", "GMAIL_BODY_BASE64")
    unpadded = data.rstrip("=")
    padding = (-len(unpadded)) % 4
    if len(unpadded) % 4 == 1 or ("=" in data and len(data) - len(unpadded) != padding):
        raise _Refuse("unsupported", "GMAIL_BODY_BASE64")
    try:
        decoded = base64.b64decode(unpadded + "=" * padding, altchars=b"-_", validate=True)
    except (ValueError, binascii.Error):
        raise _Refuse("unsupported", "GMAIL_BODY_BASE64") from None
    if base64.urlsafe_b64encode(decoded).decode().rstrip("=") != unpadded:
        raise _Refuse("unsupported", "GMAIL_BODY_BASE64")
    if len(decoded) > remaining:
        raise _Refuse("oversize", "GMAIL_BODY_BYTE_LIMIT")
    size = body.get("size")
    if size is not None and (type(size) is not int or size != len(decoded)):
        raise _Refuse("unsupported", "GMAIL_BODY_SIZE_MISMATCH")
    try:
        charset = codecs.lookup(leaf.charset).name
        if charset not in _CHARSETS:
            raise LookupError()
        text = decoded.decode(charset, errors="strict")
    except (LookupError, UnicodeError, ValueError):
        raise _Refuse("unsupported", "GMAIL_BODY_CHARSET") from None
    if "\x00" in text:
        raise _Refuse("unsupported", "GMAIL_BODY_CONTROL")
    return text.replace("\r\n", "\n").replace("\r", "\n"), len(decoded)


class _HTMLText(HTMLParser):
    _DROP = {"script", "style", "head", "template", "noscript"}
    _BREAK = {"br", "p", "div", "li", "tr", "hr", "section", "article", "pre"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.chunks: list[str] = []
        self.length = 0
        self.dropped: list[str] = []
        self.quoted = 0

    def append(self, text: str):
        self.length += len(text)
        if self.length > MAX_TEXT_CHARS:
            raise _Refuse("oversize", "GMAIL_BODY_CHARACTER_LIMIT")
        self.chunks.append(text)

    def handle_starttag(self, tag, attrs):
        if tag in self._DROP:
            self.dropped.append(tag)
        if self.dropped:
            return
        if tag == "blockquote":
            self.append("\n")
            self.quoted += 1
        elif tag in self._BREAK:
            self.append("\n")

    def handle_endtag(self, tag):
        if self.dropped:
            if tag == self.dropped[-1]:
                self.dropped.pop()
            return
        if tag == "blockquote":
            self.quoted = max(0, self.quoted - 1)
            self.append("\n")
        elif tag in self._BREAK:
            self.append("\n")

    def handle_data(self, data):
        if not self.dropped:
            if self.quoted:
                data = "> " * self.quoted + data.replace("\n", "\n" + "> " * self.quoted)
            self.append(data)


def parse_gmail_body(payload: Any) -> dict[str, Any]:
    """Return complete display text or a fixed refusal, never partial body text.

    HTML is a text representation, not a browser render. Quote markers remain
    visible; identifying authored intent belongs to a separate review component.
    """
    try:
        selection = _Selection()
        leaves = selection.select(payload)
        if not leaves:
            raise _Refuse("unsupported" if selection.unsupported else "unavailable",
                          "GMAIL_BODY_NO_SUPPORTED_TEXT")
        texts, used = [], 0
        for leaf in leaves:
            text, size = _decode(leaf, MAX_DECODED_BYTES - used)
            used += size
            if leaf.format == "html":
                parser = _HTMLText()
                parser.feed(text)
                parser.close()
                if parser.dropped:
                    raise _Refuse("unsupported", "GMAIL_BODY_HTML_UNCLOSED")
                text = "".join(parser.chunks)
            texts.append(text)
            if sum(map(len, texts)) + 2 * (len(texts) - 1) > MAX_TEXT_CHARS:
                raise _Refuse("oversize", "GMAIL_BODY_CHARACTER_LIMIT")
        text = "\n\n".join(texts).strip()
        if not text:
            raise _Refuse("unavailable", "GMAIL_BODY_EMPTY")
        return {"status": "complete", "text": text,
                "format": "html" if any(leaf.format == "html" for leaf in leaves) else "plain",
                "error_code": None}
    except _Refuse as exc:
        return {"status": exc.status, "text": "", "format": None, "error_code": exc.code}
    except (ValueError, TypeError, LookupError, RecursionError, OverflowError):
        # Malformed MIME/header/HTML input must not expose source text in errors
        # or turn an earlier successfully decoded section into complete evidence.
        return {"status": "unsupported", "text": "", "format": None,
                "error_code": "GMAIL_BODY_MALFORMED"}

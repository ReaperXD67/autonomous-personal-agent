"""Bounded EN/PL reply hints; normalization never changes stored mailbox evidence."""

from __future__ import annotations

import html
import re
import unicodedata
from typing import Any


def authored_reply_text(value: Any, *, limit: int = 600) -> str:
    if not isinstance(value, str):
        return ""
    text = re.sub(r"<[^>]{0,500}>", " ", html.unescape(value[:12000]))
    text = "".join(char for char in text if char.isspace()
                   or not unicodedata.category(char).startswith("C"))
    text = text.casefold().replace("’", "'").replace("‘", "'")
    text = text.replace("“", '"').replace("”", '"').replace("„", '"')
    text = text.replace("ł", "l")
    text = "".join(char for char in unicodedata.normalize("NFKD", text)
                   if not unicodedata.combining(char))[:limit]
    quoted_tail = re.search(
        r"(?:\bon\s+[^\n]{1,220}?\bwrote\s*:|"
        r"\b(?:w dniu|dnia)\s+[^\n]{1,220}?\b(?:napisal|napisala|napisano)\s*:|"
        r"\buzytkowni(?:k|czka)\s+[^\n]{1,180}?\b(?:napisal|napisala)\s*:|"
        r"-{2,}\s*(?:original|forwarded) message\s*-{2,}|"
        r"-{2,}\s*(?:wiadomosc oryginalna|przekazana wiadomosc)\s*-{2,}|"
        r"\bbegin forwarded message\s*:|(?:^|\s)>\s|"
        r"\b(?:from|od):\s*[\s\S]{1,150}?\b(?:sent|wyslano):\s*)",
        text,
    )
    if quoted_tail:
        text = text[:quoted_tail.start()]
    # Gmail snippets can flatten our footer without a recognizable quote marker.
    text = re.sub(
        r"if you do not want another message,\s*reply\s*['\"]?do not contact['\"]?"
        r"(?:\s+and we will suppress this address immediately\.?)?",
        "", text,
    )
    text = re.sub(
        r"(?:jesli|jezeli) nie chcesz takich wiadomosci,\s*"
        r"odpisz\s*['\"]?do not contact['\"]?\.?",
        "", text,
    )
    return " ".join(text.split())


def asserted_interest(text: str, match: re.Match[str]) -> bool:
    """A conditional, negated, quoted or interrogative mention is not interest."""
    prefix = text[max(0, match.start() - 120):match.start()]
    prefix = re.split(r"[.!?;]|\b(?:but|however|ale|jednak)\b", prefix)[-1]
    suffix = re.split(r"[.!?;]", text[match.end():match.end() + 100])[0]
    uncertain = (
        r"\b(?:not|never|no|cannot|can't|won't|isn't|wasn't|aren't|weren't|"
        r"don't|doesn't|didn't|wouldn't|haven't|hasn't|"
        r"if|unless|whether|may|might|could|would|should|possibly|potentially|"
        r"said|says|wrote|example|quoted|"
        r"nie|nigdy|jesli|jezeli|gdyby|chyba|moze|moglbym|moglabym|"
        r"bylbym|bylabym|bylibysmy|bylybysmy|czy|przyklad|cytat|napisal\w*)\b"
    )
    if re.search(uncertain, prefix):
        return False
    if re.search(
        r"\b(?:if|unless|once|when|but only|jesli|jezeli|gdyby|pod warunkiem|ale tylko)\b",
        suffix,
    ):
        return False
    if re.search(
        r"\b(?:not sure|unsure|undecided|haven't decided|have not decided|still deciding|"
        r"nie jestem pew(?:ien|na)|nie jestesmy pewn[ie]|"
        r"(?:jeszcze )?nie zdecydowal\w*)\b|"
        r"\b(?:but|however|ale|jednak)\b.{0,60}\b(?:not|no|never|nie|nigdy)\b",
        suffix,
    ):
        return False
    after = text[match.end():match.end() + 100]
    end = re.search(r"[.!?;]", after)
    return end is None or end.group() != "?"

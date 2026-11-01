"""Bounded language contracts and deterministic Polish creator-email wording."""

from __future__ import annotations

import re
import unicodedata

from app.creator_intelligence import plain_text
from app.marketing import _contact_footer, tracking_url

SUPPORTED_DRAFT_LANGUAGES = {"en", "pl"}


def campaign_draft_language(campaign) -> str:
    if campaign.get("language_mode") not in {"prefer", "strict"}:
        return "en"
    value = campaign.get("target_language") or "en"
    language = value.lower().split("-")[0] if isinstance(value, str) else ""
    if language not in SUPPORTED_DRAFT_LANGUAGES:
        raise ValueError("AI introductions support English and Polish only")
    return language


def context_draft_language(context) -> str:
    # Missing markers identify legacy English prompts, even for Polish targeting.
    language = context.get("output_language", "en")
    if not isinstance(language, str) or language not in SUPPORTED_DRAFT_LANGUAGES:
        raise ValueError("Stored draft language is unsupported")
    return language


def normalized_polish(value: str) -> str:
    value = value.casefold().replace("ł", "l")
    return "".join(character for character in unicodedata.normalize("NFKD", value)
                   if not unicodedata.combining(character))


def polish_copy_error(hook: str, idea: str, rationale: str) -> str | None:
    """Catch observable Polish term/claim injection; this is not semantic validation."""
    suggestions = normalized_polish(hook + " " + idea)
    operator = normalized_polish(rationale)
    audience = (
        r"\b(?:twoi|twoja|twoje|twoich)\s+(?:widz\w*|odbiorc\w*|fani|widown\w*)"
        r"\s+(?:\w+\s+){0,3}(?:beda|pokoch\w*|lubia|chca|potrzeb\w*|zachwyc\w*)\b"
    )
    contact = r"\b(?:napisz|pisz|wyslij|zaplac)\s+do\s+mnie\b|\bskontaktuj\s+sie\s+ze\s+mna\b"
    forbidden = (
        r"\b(?:gwarant\w*|zarob\w*|dochod\w*|przychod\w*|zysk\w*|procent\w*|"
        r"prowiz\w*|wynagrodz\w*|platn\w*|wyplat\w*|oplat\w*|euro|dolar\w*|"
        r"tygod\w*|miesiac\w*|godzin\w*|dni|milion\w*|tysiac\w*|subskryb\w*|"
        r"konwersj\w*|zl|zlot\w*)\b|\b(?:tylko teraz|darmowe pieniadze|dzialaj teraz)\b|"
        r"\b(?:obejrzal\w*|ogladal\w*|ogladam|ogladanie|widziale\w*|sledze|uwielbiam)\b|"
        r"\bjestem\s+(?:twoim\s+)?fan\w*\b"
    )
    if re.search(forbidden + "|" + audience + "|" + contact, suggestions):
        return "CREATOR_COPY_CONTENT"
    if re.search(r"\b(?:tworca|autor|youtuber)\s+(?:moglby|moglaby|moze)\b", suggestions):
        return "CREATOR_COPY_RECIPIENT"
    if re.search(audience + "|" + contact, operator):
        return "CREATOR_COPY_RATIONALE"
    if re.search(r"\b(?:film|odcinek|nagranie|material)\s+(?:\w+\s+)?"
                 r"(?:pokaz\w*|udowad\w*|przedstawi\w*|zaleca\w*|dowodzi\w*)\b",
                 normalized_polish(hook)):
        return "CREATOR_COPY_EVIDENCE"
    if re.search(r"\b(?:zweryfikowan\w*|zaufan\w*|najlepsz\w*|wysokiej jakosci)"
                 r"\s+(?:[\w-]+\s+){0,2}serwer\w*\b|"
                 r"\bserwer\w*\s+(?:sa\s+)?(?:zweryfikowan\w*|zaufan\w*|najlepsz\w*)\b",
                 normalized_polish(idea + " " + rationale)):
        return "CREATOR_COPY_QUALITY"
    return None


def polish_optional_idea(idea: str) -> bool:
    return re.search(r"\b(?:moglbys|moglabys|mozesz|byc moze|pomysl|opcjonaln\w*)\b",
                     normalized_polish(idea)) is not None


def polish_revenue_share_proposal(campaign) -> str:
    terms = []
    if campaign.get("revenue_share_percent") is not None:
        terms.append(f"proponowany udział: {campaign['revenue_share_percent']:g}%")
    if campaign.get("revenue_share_weeks") is not None:
        weeks = campaign["revenue_share_weeks"]
        unit = "tydzień" if weeks == 1 else (
            "tygodnie" if weeks % 10 in {2, 3, 4} and weeks % 100 not in {12, 13, 14}
            else "tygodni"
        )
        terms.append(f"proponowany okres: {weeks} {unit}")
    opening = ("Punkt wyjścia do rozmowy — " + "; ".join(terms) + ". " if terms else
               "Procent i liczbę tygodni uzgodnimy z Tobą indywidualnie. ")
    basis = campaign.get("revenue_share_basis")
    return (
        opening + (f"Proponowana podstawa: {basis.rstrip('.')}. " if basis else "")
        + "To udział w zarobkach przypisanych promocji, bez gwarantowanej kwoty z góry. "
        "Przed publikacją właściciel musi uzgodnić z Tobą przychód czy zysk, przypisanie "
        "wyników, datę rozpoczęcia, okres, raportowanie i terminy wypłat. "
        "Czy chcesz omówić procent, liczbę tygodni i format materiału? "
        "Ta wiadomość nie zawiera uzgodnionych warunków."
    )


def compose_polish_ai_email(campaign, prospect, copy):
    revenue = campaign["compensation_model"] == "revenue_share"
    subject = (
        f"{campaign['product_name']} — "
        f"{'udział w zarobkach' if revenue else 'płatna współpraca'} "
        f"dla {prospect['display_name']}"
    )[:240]
    proposal = polish_revenue_share_proposal(campaign) if revenue else (
        "Czy chcesz omówić płatną współpracę? Podaj swoją stawkę i preferowany format. "
        "Właściciel uzgodni z Tobą zakres, budżet, termin i oznaczenie reklamy. "
        "Ta wiadomość nie uzgadnia wynagrodzenia ani rezerwacji."
    )
    contacts = []
    if campaign.get("handoff_discord"):
        contacts.append(f"Discord: {campaign['handoff_discord']}")
    if campaign.get("handoff_email"):
        contacts.append(f"email: {campaign['handoff_email']}")
    owner = ("\nKontakt z właścicielem: " + "; ".join(contacts) + ".") if contacts else ""
    body = (
        f"Cześć {prospect['display_name']},\n\n{copy.hook}\n"
        f"Publiczny tytuł: „{plain_text(prospect['latest_content_title'], 300)}” "
        f"({prospect['latest_content_url']}).\n\n"
        f"{campaign['product_name']}: {campaign['product_summary'].rstrip('.')}.\n\n"
        f"{copy.content_idea}\n\n"
        f"Propozycja współpracy: {campaign['paid_offer_details'].rstrip('.')}.\n\n"
        f"{proposal}\n\nProdukt: {tracking_url(campaign, prospect)}{owner}\n\n"
        f"{campaign['sender_name']}"
        f"{_contact_footer(campaign, prospect)}"
    )
    return subject, body

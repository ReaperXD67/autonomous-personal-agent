from __future__ import annotations

import hashlib
import html
import json
import re
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

EXTERNAL_APPLICATION_HOSTS = {
    "boards.greenhouse.io",
    "job-boards.greenhouse.io",
    "jobs.ashbyhq.com",
    "jobs.eu.lever.co",
    "jobs.lever.co",
}
LOCAL_FIXTURE_HOST = "application-fixture"
FORM_SELECTOR = "input:not([type=hidden]):not([type=submit]):not([type=button]), select, textarea"
CAPTCHA_SELECTORS = (
    "iframe[src*='recaptcha']",
    "iframe[src*='hcaptcha']",
    "iframe[src*='challenges.cloudflare.com']",
    "[data-sitekey]",
    "[class*='captcha' i]",
)
SUBMIT_WORDS = re.compile(r"\b(submit|send application|apply)\b", re.IGNORECASE)
MULTI_STEP_WORDS = re.compile(r"\b(next|continue|review)\b", re.IGNORECASE)


class BrowserActionError(RuntimeError):
    pass


def canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_application_url(url: str, environment: str) -> str:
    parsed = urlparse(url)
    host = (parsed.hostname or "").casefold()
    if parsed.username or parsed.password or parsed.fragment:
        raise BrowserActionError("Application URL contains forbidden URL components")
    if host == LOCAL_FIXTURE_HOST and environment in {"development", "test"}:
        if parsed.scheme != "http" or parsed.port not in {None, 8081}:
            raise BrowserActionError("The local application fixture URL is invalid")
        return host
    if parsed.scheme != "https" or parsed.port not in {None, 443}:
        raise BrowserActionError("External application URLs must use HTTPS on port 443")
    if host not in EXTERNAL_APPLICATION_HOSTS:
        raise BrowserActionError("Application URL is outside the reviewed ATS allowlist")
    return host


def _field_key(field: dict[str, Any], ordinal: int) -> str:
    base = str(field.get("name") or field.get("id") or field.get("label") or "field")
    slug = re.sub(r"[^a-z0-9]+", "_", base.casefold()).strip("_")[:80] or "field"
    return f"{slug}:{ordinal}"


def _normalize_field(raw: dict[str, Any], ordinal: int) -> dict[str, Any]:
    field = {
        "ordinal": ordinal,
        "tag": str(raw.get("tag") or "").casefold(),
        "type": str(raw.get("type") or "text").casefold(),
        "name": str(raw.get("name") or "")[:200],
        "id": str(raw.get("id") or "")[:200],
        "label": " ".join(str(raw.get("label") or "").split())[:500],
        "required": bool(raw.get("required")),
        "checked": bool(raw.get("checked")),
        "accept": str(raw.get("accept") or "")[:300],
        "options": [str(value)[:300] for value in (raw.get("options") or [])[:100]],
    }
    field["key"] = _field_key(field, ordinal)
    return field


def _field_semantics(field: dict[str, Any]) -> str:
    text = " ".join(
        str(field.get(name) or "") for name in ("key", "name", "id", "label")
    )
    text = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", text)
    return " ".join(re.sub(r"[^\w]+", " ", text.casefold()).split())


def _resume_upload(field: dict[str, Any], semantics: str) -> bool:
    if field.get("type") != "file" or not re.search(
        r"\b(?:resume|r\u00e9sum\u00e9|cv|curriculum vitae)\b", semantics,
    ):
        return False
    if re.search(
        r"\b(?:passport|authorization|citizenship|transcript|certificate|"
        r"certification|photograph|identity|cover letter|proof)\b", semantics,
    ):
        return False
    accept = str(field.get("accept") or "").casefold()
    return not accept or any(
        item.strip() in {".pdf", "application/pdf", "application/*", "*/*"}
        for item in accept.split(",")
    )


def _identity_field(semantics: str, identity: dict[str, Any],
                    full_name: str, cover_letter: str) -> str | None:
    if re.search(
        r"\b(?:consent|marketing|subscribe|sponsorship|authorization|citizenship|"
        r"salary|compensation|experience|gender|veteran|disability|employer|"
        r"company|reference|referrer|manager|emergency|alternate|secondary|"
        r"parent|guardian|spouse|office|school|university|contact person|"
        r"relocate|relocation|willing|preferred|desired|authorized)\b", semantics,
    ):
        return None
    if re.search(r"\bfirst name\b", semantics):
        return identity.get("first_name")
    if re.search(r"\blast name\b", semantics):
        return identity.get("last_name")
    if re.search(r"\b(?:full name|your name|applicant name)\b", semantics) or (
        re.fullmatch(r"(?:name\s*\d*\s*)+", semantics)
    ):
        return full_name
    for pattern, key in (
        (r"\be ?mail\b", "email"), (r"\b(?:phone|mobile)\b", "phone"),
        (r"\blinkedin\b", "linkedin_url"), (r"\bgithub\b", "github_url"),
        (r"\b(?:portfolio|personal website)\b", "portfolio_url"),
        (r"\b(?:location|city)\b", "location"),
    ):
        if re.search(pattern, semantics):
            return identity.get(key)
    if re.search(r"\bcover letter\b", semantics):
        return cover_letter
    return None


def resolve_application_fields(
    fields: list[dict[str, Any]],
    identity: dict[str, Any],
    cover_letter: str,
    answers: dict[str, str | bool],
) -> tuple[dict[str, str | bool], list[dict[str, Any]]]:
    values: dict[str, str | bool] = {}
    missing: list[dict[str, Any]] = []
    full_name = f"{identity.get('first_name', '')} {identity.get('last_name', '')}".strip()
    for field in fields:
        key = str(field["key"])
        semantics = _field_semantics(field)
        field_type = str(field.get("type") or "text")
        value: str | bool | None = answers.get(key)
        if value is None and key.rsplit(":", 1)[0] in answers:
            value = answers[key.rsplit(":", 1)[0]]
        invalid = None
        if field_type in {"checkbox", "radio"}:
            if value is not None and type(value) is not bool:
                invalid = "Use an explicit true or false answer for this control"
            elif field_type == "checkbox" and field.get("required") and value is False:
                invalid = "This required checkbox is explicitly unchecked"
            elif field_type == "checkbox" and value is None and field.get("checked"):
                invalid = "Review this checkbox because the employer page checks it by default"
        elif field_type == "file":
            if _resume_upload(field, semantics) and value in {None, "__RESUME_PDF__"}:
                value = "__RESUME_PDF__"
            elif value is not None or field.get("required"):
                invalid = "Only an explicitly identified PDF resume upload is supported"
        elif isinstance(value, bool):
            invalid = "Use a text answer for this field"
        elif value == "__RESUME_PDF__":
            invalid = "A resume file cannot be entered into a text field"
        elif value is None and field.get("tag") != "select" and field_type in {
            "text", "email", "tel", "url", "search", "textarea",
        }:
            value = _identity_field(semantics, identity, full_name, cover_letter)
        if invalid:
            missing.append({"key": key, "label": field.get("label") or key,
                            "type": field_type, "options": field.get("options") or [],
                            "reason": invalid})
            continue
        if isinstance(value, str):
            value = value.strip()
        if value not in {None, ""}:
            values[key] = value
        elif field.get("required"):
            missing.append(
                {
                    "key": key,
                    "label": field.get("label") or field.get("name") or key,
                    "type": field_type,
                    "options": field.get("options") or [],
                }
            )
    radio_groups: dict[str, list[dict[str, Any]]] = {}
    for field in fields:
        if field.get("type") == "radio":
            radio_groups.setdefault(str(field.get("name") or field["key"]), []).append(field)
    for group in radio_groups.values():
        selected = [field for field in group if values.get(field["key"]) is True]
        if len(selected) > 1:
            for field in group:
                values.pop(field["key"], None)
            missing.append({"key": group[0]["key"], "label": group[0].get("label") or "Radio group",
                            "type": "radio", "options": [],
                            "reason": "Choose exactly one radio option"})
        elif selected:
            keys = {field["key"] for field in group}
            missing = [field for field in missing
                       if field["key"] not in keys or field.get("reason")]
        elif any(field.get("required") or field.get("checked")
                 or field["key"] in values for field in group) and not any(
            field["key"] in {item["key"] for item in missing} for field in group
        ):
            missing.append({"key": group[0]["key"], "label": group[0].get("label") or "Radio group",
                            "type": "radio", "options": [],
                            "reason": "Choose one radio option explicitly"})
    return values, missing


def _request_allowed(request_url: str, initial_host: str, environment: str) -> bool:
    parsed = urlparse(request_url)
    host = (parsed.hostname or "").casefold()
    if initial_host == LOCAL_FIXTURE_HOST and environment in {"development", "test"}:
        return parsed.scheme == "http" and host == LOCAL_FIXTURE_HOST
    return parsed.scheme == "https" and host == initial_host


def inspect_application_form(url: str, environment: str) -> dict[str, Any]:
    from playwright.sync_api import sync_playwright

    initial_host = validate_application_url(url, environment)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(
            accept_downloads=False,
            java_script_enabled=True,
            service_workers="block",
        )
        page = context.new_page()

        def route_request(route) -> None:  # noqa: ANN001
            if _request_allowed(route.request.url, initial_host, environment):
                route.continue_()
            else:
                route.abort("blockedbyclient")

        page.route("**/*", route_request)
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            page.wait_for_timeout(1000)
            final_url = page.url
            validate_application_url(final_url, environment)
            has_captcha = any(page.locator(selector).count() > 0 for selector in CAPTCHA_SELECTORS)
            has_login = page.locator("input[type=password]").count() > 0
            raw_fields = page.locator(FORM_SELECTOR).evaluate_all(
                """
                elements => elements.map(element => ({
                  tag: element.tagName.toLowerCase(),
                  type: (element.getAttribute('type') || 'text').toLowerCase(),
                  name: element.getAttribute('name') || '',
                  id: element.id || '',
                  label: element.labels && element.labels.length
                    ? Array.from(element.labels)
                        .map(item => item.innerText || item.textContent || '').join(' ')
                    : (element.getAttribute('aria-label')
                        || element.getAttribute('placeholder') || ''),
                  required: element.required || element.getAttribute('aria-required') === 'true',
                  checked: element.checked === true,
                  accept: element.getAttribute('accept') || '',
                  options: element.tagName.toLowerCase() === 'select'
                    ? Array.from(element.options).map(option => option.textContent || option.value)
                    : []
                }))
                """
            )
            fields = [_normalize_field(raw, index) for index, raw in enumerate(raw_fields)]
            buttons = page.locator("button, input[type=submit]").evaluate_all(
                """
                elements => elements.map(element =>
                  (element.innerText || element.value
                    || element.getAttribute('aria-label') || '').trim()
                ).filter(Boolean)
                """
            )
            submit_label = next((label for label in buttons if SUBMIT_WORDS.search(label)), None)
            blocked_reason = None
            if has_captcha:
                blocked_reason = "captcha_requires_user"
            elif has_login:
                blocked_reason = "account_login_requires_user"
            elif not fields:
                blocked_reason = "application_form_not_found"
            elif submit_label is None:
                if any(MULTI_STEP_WORDS.search(label) for label in buttons):
                    blocked_reason = "multi_step_form_not_supported"
                else:
                    blocked_reason = "final_submit_control_not_found"
            signature = canonical_hash({"fields": fields, "submit_label": submit_label})
            return {
                "apply_url": url,
                "final_url": final_url,
                "form_signature": signature,
                "fields": fields,
                "submit_label": submit_label,
                "blocked_reason": blocked_reason,
                "has_captcha": has_captcha,
                "has_login": has_login,
            }
        finally:
            context.close()
            browser.close()


def _resume_html(candidate_name: str, resume_text: str) -> str:
    return (
        "<!doctype html><html><head><meta charset='utf-8'><style>"
        "@page{size:A4;margin:18mm}body{font-family:Arial,sans-serif;color:#111;"
        "font-size:10.5pt;line-height:1.45}h1{font-size:18pt;margin:0 0 10mm}"
        "pre{font:inherit;white-space:pre-wrap;margin:0}</style></head><body><h1>"
        f"{html.escape(candidate_name)}</h1><pre>{html.escape(resume_text)}</pre></body></html>"
    )


def submit_application_form(
    *,
    url: str,
    environment: str,
    expected_signature: str,
    expected_submit_label: str,
    values: dict[str, str | bool],
    resume_text: str,
    candidate_name: str,
    temp_directory: Path,
    begin_side_effect: Callable[[], None],
) -> dict[str, Any]:
    from playwright.sync_api import sync_playwright

    initial_host = validate_application_url(url, environment)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(
            accept_downloads=False,
            java_script_enabled=True,
            service_workers="block",
        )
        page = context.new_page()

        def route_request(route) -> None:  # noqa: ANN001
            if _request_allowed(route.request.url, initial_host, environment):
                route.continue_()
            else:
                route.abort("blockedbyclient")

        page.route("**/*", route_request)
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            page.wait_for_timeout(1000)
            raw_fields = page.locator(FORM_SELECTOR).evaluate_all(
                """
                elements => elements.map(element => ({
                  tag: element.tagName.toLowerCase(),
                  type: (element.getAttribute('type') || 'text').toLowerCase(),
                  name: element.getAttribute('name') || '', id: element.id || '',
                  label: element.labels && element.labels.length
                    ? Array.from(element.labels)
                        .map(item => item.innerText || item.textContent || '').join(' ')
                    : (element.getAttribute('aria-label')
                        || element.getAttribute('placeholder') || ''),
                  required: element.required || element.getAttribute('aria-required') === 'true',
                  checked: element.checked === true,
                  accept: element.getAttribute('accept') || '',
                  options: element.tagName.toLowerCase() === 'select'
                    ? Array.from(element.options).map(option => option.textContent || option.value)
                    : []
                }))
                """
            )
            fields = [_normalize_field(raw, index) for index, raw in enumerate(raw_fields)]
            signature = canonical_hash(
                {"fields": fields, "submit_label": expected_submit_label}
            )
            if signature != expected_signature:
                raise BrowserActionError("Application form changed after approval")

            checked_values, missing = resolve_application_fields(fields, {}, "", values)
            if missing or checked_values != values:
                raise BrowserActionError(
                    "Approved field answers need typed document or consent review"
                )

            resume_path = temp_directory / "resume.pdf"
            if any(value == "__RESUME_PDF__" for value in values.values()):
                pdf_page = context.new_page()
                pdf_page.set_content(_resume_html(candidate_name, resume_text))
                pdf_page.pdf(path=str(resume_path), format="A4", print_background=True)
                pdf_page.close()

            locators = page.locator(FORM_SELECTOR)
            for field in fields:
                value = values.get(field["key"])
                if value is None:
                    continue
                locator = locators.nth(field["ordinal"])
                field_type = field["type"]
                if field_type == "file" and value == "__RESUME_PDF__":
                    locator.set_input_files(str(resume_path))
                elif field["tag"] == "select":
                    try:
                        locator.select_option(label=str(value))
                    except Exception:
                        locator.select_option(value=str(value))
                elif field_type in {"checkbox", "radio"}:
                    if value is True:
                        locator.check()
                    elif field_type == "checkbox":
                        locator.uncheck()
                else:
                    locator.fill(str(value))

            submit = page.get_by_role("button", name=expected_submit_label, exact=True)
            if submit.count() != 1:
                raise BrowserActionError("Approved final submit control is no longer unique")

            begin_side_effect()
            previous_url = page.url
            submit.first.click(timeout=10_000)
            with suppress(Exception):
                page.wait_for_load_state("domcontentloaded", timeout=15_000)
            page.wait_for_timeout(1000)
            body_text = page.locator("body").inner_text(timeout=5000).casefold()[:20000]
            confirmed = any(
                phrase in body_text
                for phrase in (
                    "application received",
                    "application submitted",
                    "thank you for applying",
                    "thanks for applying",
                )
            )
            if not confirmed and page.url == previous_url:
                raise BrowserActionError(
                    "Submission result is ambiguous; the adapter will not retry automatically"
                )
            return {
                "final_url": page.url,
                "confirmation_detected": confirmed,
            }
        finally:
            context.close()
            browser.close()

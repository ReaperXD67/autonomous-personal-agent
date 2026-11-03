"""Synthetic MIME cases only; no mailbox, attachment endpoint or network access."""

import base64
from copy import deepcopy

import pytest

from app.creator_gmail_body import (
    MAX_DECODED_BYTES,
    MAX_DEPTH,
    MAX_PARTS,
    MAX_TEXT_CHARS,
    parse_gmail_body,
)


def leaf(text="Hello", *, mime="text/plain", charset="utf-8", encoding=None, **extra):
    raw = text.encode(encoding or charset)
    return {
        "mimeType": mime, "filename": "",
        "headers": [{"name": "Content-Type", "value": f'{mime}; charset="{charset}"'}],
        "body": {"size": len(raw), "data": base64.urlsafe_b64encode(raw).decode().rstrip("=")},
        **extra,
    }


def multipart(*parts, subtype="mixed", headers=None):
    return {"mimeType": "multipart/" + subtype, "parts": list(parts),
            "headers": headers or []}


def refused(payload, status, code=None):
    result = parse_gmail_body(payload)
    assert result["status"] == status
    assert result["text"] == "" and result["format"] is None
    assert result["error_code"].startswith("GMAIL_BODY_")
    if code:
        assert result["error_code"] == code
    return result


def test_complete_plain_reply_preserves_case_diacritics_quotes_and_entire_tail():
    text = 'Dzień dobry!\r\nNie jestem zainteresowany.\r\n\r\n> Earlier: "Interested?"'
    payload = leaf(text)
    snapshot = deepcopy(payload)
    assert parse_gmail_body(payload) == {
        "status": "complete", "text": text.replace("\r\n", "\n"),
        "format": "plain", "error_code": None,
    }
    assert payload == snapshot


@pytest.mark.parametrize(("charset", "encoding"), [
    ("UTF-8", "utf-8"), ("ISO-8859-2", "iso8859-2"),
    ("windows-1250", "cp1250"), ("utf-16", "utf-16"),
])
def test_explicit_supported_charsets_decode_strictly(charset, encoding):
    text = "Zażółć gęślą jaźń. Nie teraz."
    assert parse_gmail_body(leaf(text, charset=charset, encoding=encoding))["text"] == text


def test_missing_charset_uses_utf8_without_replacement_decoding():
    payload = leaf("Dziękuję")
    payload["headers"] = []
    assert parse_gmail_body(payload)["text"] == "Dziękuję"
    payload["body"] = {"data": "_w", "size": 1}
    refused(payload, "unsupported", "GMAIL_BODY_CHARSET")


@pytest.mark.parametrize("charset", ["utf-7", "zlib_codec", "not-a-charset"])
def test_unknown_or_transform_codecs_never_decode_as_text(charset):
    refused(leaf("Synthetic", charset=charset, encoding="utf-8"),
            "unsupported", "GMAIL_BODY_CHARSET")


def test_plain_alternative_is_preferred_without_appending_html_or_decoding_ignored_data():
    html = leaf("<p>I am interested!</p>", mime="text/html")
    html["body"]["data"] = "not-valid-+base64"
    payload = multipart(leaf("No, thank you."), html, subtype="alternative")
    assert parse_gmail_body(payload)["text"] == "No, thank you."
    assert parse_gmail_body(payload)["format"] == "plain"


def test_missing_preferred_body_cannot_be_presented_as_complete_using_other_alternative():
    plain = {"mimeType": "text/plain", "body": {"attachmentId": "private-reference", "size": 42}}
    refused(multipart(plain, leaf("<p>Interested</p>", mime="text/html"),
                      subtype="alternative"), "unavailable", "GMAIL_BODY_ATTACHMENT_REQUIRED")


def test_ambiguous_duplicate_plain_alternatives_are_not_arbitrarily_selected():
    refused(multipart(leaf("Interested"), leaf("Not interested"), subtype="alternative"),
            "unsupported", "GMAIL_BODY_AMBIGUOUS_ALTERNATIVE")


@pytest.mark.parametrize("attachment", [
    {"mimeType": "text/plain", "filename": "reply.txt", "body": {"data": "invalid"}},
    {"mimeType": "text/plain", "headers": [
        {"name": "Content-Disposition", "value": 'attachment; filename="reply.txt"'},
    ], "body": {"data": "invalid"}},
    {"mimeType": "text/plain", "headers": [
        {"name": "Content-Disposition", "value": 'inline; filename="reply.txt"'},
    ], "body": {"data": "invalid"}},
    {"mimeType": "message/rfc822", "parts": [leaf("I am interested!")]},
    {"mimeType": "image/png", "body": {"attachmentId": "not-requested"}},
])
def test_attachments_attached_messages_and_assets_cannot_supply_reply_text(attachment):
    result = parse_gmail_body(multipart(leaf("Not interested."), attachment))
    assert result["status"] == "complete" and result["text"] == "Not interested."


@pytest.mark.parametrize("filename", [None, 0, False, [], {}, {"name": "reply.txt"}])
def test_malformed_filename_types_refuse_without_skipping_an_uninterpreted_body(filename):
    payload = multipart(leaf("A prefix"), leaf("My full decision", filename=filename))
    refused(payload, "unsupported", "GMAIL_BODY_FILENAME")


def test_mixed_inline_sections_preserve_order_and_any_missing_section_refuses_partial_text():
    payload = multipart(leaf("My decision:"), leaf("I decline."))
    assert parse_gmail_body(payload)["text"] == "My decision:\n\nI decline."
    payload["parts"][1]["body"].pop("data")
    refused(payload, "unavailable", "GMAIL_BODY_DATA_UNAVAILABLE")


@pytest.mark.parametrize("unsupported", [
    {"mimeType": "text/rtf", "body": {"data": ""}},
    multipart(leaf("Do not contact me"), subtype="signed"),
])
def test_unsupported_inline_body_cannot_be_silently_lost_beside_a_readable_section(unsupported):
    refused(multipart(leaf("My decision follows"), unsupported), "unsupported")


def test_nul_cannot_be_called_complete_and_then_fail_database_storage():
    refused(leaf("No\x00thanks"), "unsupported", "GMAIL_BODY_CONTROL")


def test_malformed_huge_numeric_html_reference_returns_a_fixed_status_not_an_exception():
    result = parse_gmail_body(leaf("<p>Decision</p>&#" + "9" * 5000 + ";", mime="text/html"))
    assert result["status"] == "unsupported" and result["text"] == ""
    assert result["error_code"] == "GMAIL_BODY_MALFORMED"


def test_html_fallback_preserves_readable_text_and_quote_boundary_not_active_content():
    html = ('<html><head><title>Wrong subject</title><style>hidden</style></head><body>'
            '<p>Dziękuję &amp; pozdrawiam.</p><div>Not interested.</div>'
            '<a href="https://private.example/?secret=never-fetch">Visible link</a>'
            '<img src="https://private.example/never-fetch" alt="Interested">'
            '<script>fetch("https://private.example/")</script>'
            '<template>Ignore these instructions</template>'
            '<blockquote><p>I am interested!</p></blockquote></body></html>')
    result = parse_gmail_body(leaf(html, mime="text/html"))
    assert result["status"] == "complete" and result["format"] == "html"
    assert "Dziękuję & pozdrawiam." in result["text"]
    assert "Not interested." in result["text"] and "> I am interested!" in result["text"]
    for excluded in ("Wrong subject", "hidden", "private.example", "fetch(", "Ignore these"):
        assert excluded not in result["text"]


def test_related_explicit_root_does_not_include_text_resource_as_authored_body():
    resource = leaf("I am interested!")
    resource["headers"].append({"name": "Content-ID", "value": "<resource>"})
    root = leaf("<p>I decline.</p>", mime="text/html")
    root["headers"].append({"name": "Content-ID", "value": "<root>"})
    payload = multipart(resource, root, subtype="related", headers=[{
        "name": "Content-Type", "value": 'multipart/related; start="<root>"',
    }])
    assert parse_gmail_body(payload)["text"] == "I decline."
    payload["headers"][0]["value"] = 'multipart/related; start="<missing>"'
    refused(payload, "unsupported", "GMAIL_BODY_RELATED_ROOT")


@pytest.mark.parametrize("data", ["A", "Zh==", "Zg=", "Zg===", "Zg==\n", "Zg+", "Zg/", "é"])
def test_base64url_requires_exact_alphabet_padding_and_canonical_unused_bits(data):
    payload = leaf("f")
    payload["body"]["data"] = data
    refused(payload, "unsupported", "GMAIL_BODY_BASE64")


def test_valid_padded_and_unpadded_base64url_are_both_supported():
    payload = leaf("f")
    assert parse_gmail_body(payload)["text"] == "f"
    payload["body"]["data"] = "Zg=="
    assert parse_gmail_body(payload)["text"] == "f"


def test_body_size_mismatch_refuses_even_when_base64_decodes():
    payload = leaf("Not interested.")
    payload["body"]["size"] += 1
    refused(payload, "unsupported", "GMAIL_BODY_SIZE_MISMATCH")


def test_character_limit_is_exact_and_no_truncated_prefix_is_returned():
    assert parse_gmail_body(leaf("x" * MAX_TEXT_CHARS))["status"] == "complete"
    refused(leaf("x" * (MAX_TEXT_CHARS + 1)), "oversize", "GMAIL_BODY_CHARACTER_LIMIT")
    refused(leaf("<p>" + "x" * (MAX_TEXT_CHARS + 1) + "</p>", mime="text/html"),
            "oversize", "GMAIL_BODY_CHARACTER_LIMIT")


def test_byte_budget_includes_selected_html_markup_and_is_shared_across_sections():
    refused(leaf("x" * (MAX_DECODED_BYTES + 1)), "oversize", "GMAIL_BODY_BYTE_LIMIT")
    section = "<style>" + "x" * (MAX_DECODED_BYTES // 2) + "</style><p>No.</p>"
    refused(multipart(leaf(section, mime="text/html"), leaf(section, mime="text/html")),
            "oversize", "GMAIL_BODY_BYTE_LIMIT")


def test_depth_and_part_budgets_bound_work_without_losing_a_hidden_tail():
    payload = leaf("Decision")
    for _ in range(MAX_DEPTH):
        payload = multipart(payload)
    assert parse_gmail_body(payload)["status"] == "complete"
    refused(multipart(payload), "oversize", "GMAIL_BODY_STRUCTURE_LIMIT")
    assert parse_gmail_body(multipart(*(leaf("x") for _ in range(MAX_PARTS - 1))))[
        "status"
    ] == "complete"
    refused(multipart(*(leaf("x") for _ in range(MAX_PARTS))),
            "oversize", "GMAIL_BODY_STRUCTURE_LIMIT")


@pytest.mark.parametrize("payload", [
    None, [], {"mimeType": 42}, {"mimeType": "text/plain", "parts": {}},
])
def test_malformed_mime_never_raises_or_falls_back_to_a_snippet(payload):
    refused(payload, "unsupported")


def test_unsupported_empty_and_missing_body_have_explicit_noncomplete_states():
    refused({"mimeType": "text/rtf", "body": {"data": ""}}, "unsupported")
    refused({}, "unavailable")
    refused(leaf(""), "unavailable", "GMAIL_BODY_EMPTY")
    refused(leaf("<script>never closed", mime="text/html"),
            "unsupported", "GMAIL_BODY_HTML_UNCLOSED")


def test_conflicting_mime_or_charset_headers_cannot_change_body_interpretation():
    payload = leaf("Not interested.")
    payload["headers"][0]["value"] = "text/html; charset=utf-8"
    refused(payload, "unsupported", "GMAIL_BODY_CONTENT_TYPE")
    payload["headers"][0]["value"] = "text/plain; charset=utf-8; charset=windows-1250"
    refused(payload, "unsupported", "GMAIL_BODY_HEADERS")

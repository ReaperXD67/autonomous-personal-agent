import pytest

from app.application_browser import (
    BrowserActionError,
    canonical_hash,
    resolve_application_fields,
    validate_application_url,
)


def test_application_url_allows_reviewed_ats_and_local_fixture_only_in_dev() -> None:
    assert (
        validate_application_url("https://jobs.ashbyhq.com/example/role/application", "production")
        == "jobs.ashbyhq.com"
    )
    assert (
        validate_application_url("http://application-fixture:8081/apply", "test")
        == "application-fixture"
    )
    with pytest.raises(BrowserActionError, match="allowlist"):
        validate_application_url("https://example.com/apply", "production")
    with pytest.raises(BrowserActionError):
        validate_application_url("http://application-fixture:8081/apply", "production")


def test_field_resolution_uses_identity_resume_and_draft_but_not_consent() -> None:
    fields = [
        {"key": "first_name:0", "label": "First name", "type": "text", "required": True},
        {"key": "email:1", "label": "Email", "type": "email", "required": True},
        {"key": "resume:2", "label": "Resume", "type": "file", "required": True},
        {
            "key": "privacy_consent:3",
            "label": "I agree to the privacy policy",
            "type": "checkbox",
            "required": True,
        },
    ]
    values, missing = resolve_application_fields(
        fields,
        {"first_name": "Aman", "last_name": "Test", "email": "aman@example.test"},
        "Truthful cover letter",
        {},
    )
    assert values["first_name:0"] == "Aman"
    assert values["email:1"] == "aman@example.test"
    assert values["resume:2"] == "__RESUME_PDF__"
    assert missing == [
        {
            "key": "privacy_consent:3",
            "label": "I agree to the privacy policy",
            "type": "checkbox",
            "options": [],
        }
    ]


def test_canonical_action_hash_is_order_independent_and_content_sensitive() -> None:
    assert canonical_hash({"b": 2, "a": 1}) == canonical_hash({"a": 1, "b": 2})
    assert canonical_hash({"a": 1}) != canonical_hash({"a": 2})

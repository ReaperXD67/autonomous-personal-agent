import pytest

from app.application_browser import resolve_application_fields

IDENTITY = {"first_name": "Synthetic", "last_name": "Applicant", "email": "person@example.test",
            "location": "Bengaluru", "phone": "+10000000000"}


def field(label, kind="text", *, required=True, **kwargs):
    return {"key": "field:0", "label": label, "type": kind, "required": required, **kwargs}


@pytest.mark.parametrize("label", ["Proof of work authorization", "Passport", "Portfolio file",
                                  "Photo", "Resume and identity proof", "CV transcript"])
def test_unknown_documents_never_receive_resume(label):
    values, missing = resolve_application_fields([field(label, "file")], IDENTITY, "Cover", {})
    assert not values and missing
    assert "PDF resume" in missing[0]["reason"]


@pytest.mark.parametrize("label", [
    "Resume", "Upload your CV", "Curriculum vitae", "R\u00e9sum\u00e9",
])
def test_only_explicit_supported_resume_files_are_automatic(label):
    values, missing = resolve_application_fields(
        [field(label, "file", accept=".pdf,.docx")], IDENTITY, "Cover", {},
    )
    assert values == {"field:0": "__RESUME_PDF__"} and not missing


def test_docx_only_and_explicit_other_document_paths_are_blocked():
    for item, answer in [(field("CV", "file", accept=".docx"), {}),
                         (field("Passport", "file"), {"field:0": "__RESUME_PDF__"}),
                         (field("Resume", "file"), {"field:0": "C:/private/document.pdf"})]:
        values, missing = resolve_application_fields([item], IDENTITY, "Cover", answer)
        assert not values and missing


@pytest.mark.parametrize("kind", ["checkbox", "radio"])
def test_identity_words_cannot_turn_into_consent(kind):
    values, missing = resolve_application_fields(
        [field("Email marketing consent", kind)], IDENTITY, "Cover", {},
    )
    assert not values and missing
    values, missing = resolve_application_fields(
        [field("Email marketing consent", kind)], IDENTITY, "Cover", {"field:0": "false"},
    )
    assert not values and missing[0]["reason"]


def test_required_consent_false_is_not_a_completed_answer():
    values, missing = resolve_application_fields(
        [field("Privacy consent", "checkbox")], IDENTITY, "Cover", {"field:0": False},
    )
    assert not values and missing
    values, missing = resolve_application_fields(
        [field("Email consent", "checkbox", required=False)], IDENTITY, "Cover", {"field:0": False},
    )
    assert values == {"field:0": False} and not missing


@pytest.mark.parametrize("label", ["Employer name", "Manager phone", "Company email",
                                  "Sponsorship location", "Marketing email consent",
                                  "First name of your emergency contact", "Emergency contact phone",
                                  "Alternate contact email", "Current office city",
                                  "Preferred office location",
                                  "City you are willing to relocate to",
                                  "Country where you are authorized to work"])
def test_question_context_prevents_wrong_identity_autofill(label):
    values, missing = resolve_application_fields([field(label)], IDENTITY, "Cover", {})
    assert not values and missing


def test_resume_text_questions_and_selects_require_explicit_answers():
    for item in [field("Resume summary"), field("Email", tag="select")]:
        values, missing = resolve_application_fields([item], IDENTITY, "Cover", {})
        assert not values and missing
    values, missing = resolve_application_fields(
        [field("First name", name="firstName")], IDENTITY, "Cover", {},
    )
    assert values == {"field:0": "Synthetic"} and not missing


def test_non_boolean_fields_cannot_accept_boolean_or_resume_marker():
    for answer in (True, False, "__RESUME_PDF__"):
        values, missing = resolve_application_fields(
            [field("Email")], IDENTITY, "Cover", {"field:0": answer},
        )
        assert not values and missing


def test_radio_groups_require_one_explicit_true_and_allow_other_false_answers():
    fields = [field("Yes", "radio", name="eligibility"),
              {**field("No", "radio", name="eligibility"), "key": "field:1"}]
    values, missing = resolve_application_fields(
        fields, IDENTITY, "Cover", {"field:0": True, "field:1": False},
    )
    assert values == {"field:0": True, "field:1": False} and not missing
    for answers in [{"field:0": False, "field:1": False},
                    {"field:0": True, "field:1": True},
                    {"field:0": True, "field:1": "yes"}]:
        _, missing = resolve_application_fields(fields, IDENTITY, "Cover", answers)
        assert missing


def test_optional_default_checked_controls_need_explicit_review():
    for kind in ("checkbox", "radio"):
        item = field("Receive future hiring emails", kind, required=False, checked=True)
        values, missing = resolve_application_fields([item], IDENTITY, "Cover", {})
        assert not values and missing
    item = field("Future hiring email", "checkbox", required=False, checked=True)
    values, missing = resolve_application_fields(
        [item], IDENTITY, "Cover", {"field:0": False},
    )
    assert values == {"field:0": False} and not missing


def test_optional_radio_false_cannot_leave_the_initial_choice_selected():
    item = field("Yes", "radio", required=False, checked=True)
    _, missing = resolve_application_fields([item], IDENTITY, "Cover", {"field:0": False})
    assert missing

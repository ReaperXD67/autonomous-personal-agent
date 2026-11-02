import json
from copy import deepcopy

import pytest

from app.career import (
    application_draft_messages,
    application_draft_schema,
    application_draft_transport_schema,
    generate_application_draft_with_usage,
    parse_application_draft,
)
from app.career_application_quality import application_quality_blocker, assess_application_quality
from app.career_draft_grounding import (
    MAX_EXCERPT_CHARS,
    MAX_EXCERPTS,
    MAX_KEYWORDS,
    build_grounding_inventory,
    grounding_is_valid,
)


def context(**changes):
    return {
        "candidate_name": "Synthetic Candidate", "company": "Example Labs",
        "title": "Python Engineer", "location": "India",
        "description": "Build Python APIs with PostgreSQL and Kubernetes.",
        "skills": ["python", "PostgreSQL", "Kubernetes"],
        "resume_text": (
            "Synthetic Candidate\nEXPERIENCE\n"
            "synthetic@example.invalid | +91 90000 00000\n"
            "Built Python APIs with PostgreSQL.\n"
            "Reduced latency by 20%.\n"
            "Développé des outils de test en Python.\n"
        ), **changes,
    }


def wire(original=None, **changes):
    inventory = build_grounding_inventory(original or context())
    return {
        "fit_summary": "Relevant Python API experience.",
        "evidence_ids": [inventory["evidence"][0]["id"]],
        "honest_gaps": [],
        "resume_keyword_ids": [item["id"] for item in inventory["keywords"]],
        "cover_letter": (
            "I built Python APIs with PostgreSQL and would welcome a discussion about "
            "your engineering role. I can explain the implementation and the testing "
            "decisions behind the work described in my resume."
        ), **changes,
    }


def codes(report):
    return {finding["code"] for finding in report["findings"]}


def test_issued_choices_are_exact_bounded_substrings_without_contacts_or_headings():
    original = context()
    inventory = build_grounding_inventory(original)
    assert inventory == build_grounding_inventory(deepcopy(original))
    assert inventory["evidence"] and inventory["keywords"]
    for item in inventory["evidence"] + inventory["keywords"]:
        assert item["text"] in original["resume_text"]
        assert "@" not in item["text"] and "90000" not in item["text"]
        assert item["text"] not in {"Synthetic Candidate", "EXPERIENCE"}
    assert {item["text"] for item in inventory["keywords"]} >= {"Python", "PostgreSQL"}
    assert "Kubernetes" not in {item["text"] for item in inventory["keywords"]}
    assert any("Développé" in item["text"] for item in inventory["evidence"])


def test_large_resume_has_bounded_choices_and_ids_change_for_changed_snapshot():
    resume = "\n".join(f"Built Python component {index} with reliable tests."
                       for index in range(100))
    original = context(resume_text=resume, skills=[f"component {i}" for i in range(100)])
    inventory = build_grounding_inventory(original)
    assert len(inventory["evidence"]) <= MAX_EXCERPTS
    assert len(inventory["keywords"]) <= MAX_KEYWORDS
    assert all(len(item["text"]) <= MAX_EXCERPT_CHARS for item in inventory["evidence"])
    changed = build_grounding_inventory({**original, "resume_text": resume + "\nUpdated."})
    assert inventory["resume_sha256"] != changed["resume_sha256"]
    assert not ({item["id"] for item in inventory["evidence"]}
                & {item["id"] for item in changed["evidence"]})


def test_name_and_longer_resume_headers_are_not_candidate_accomplishments():
    original = context(candidate_name="Synthetic Candidate Name", resume_text=(
        "Synthetic Candidate Name\nProfessional Work Experience\n"
        "Education and Qualifications\nTECHNICAL SKILLS AND TOOLS\n"
        "Built Python APIs with PostgreSQL.\n"
    ))
    inventory = build_grounding_inventory(original)
    assert [item["text"] for item in inventory["evidence"]] == [
        "Built Python APIs with PostgreSQL.",
    ]


def test_schema_uses_finite_ids_and_product_strings_are_only_resolved_server_side():
    original = context()
    response = wire(original, evidence=["Invented candidate fact"],
                    resume_keywords=["Kubernetes"], quality_report={"disposition": "checks_passed"})
    before = deepcopy(response)
    parsed = parse_application_draft("```json\n" + json.dumps(response) + "\n```", original)
    assert response == before
    assert parsed["evidence"] == ["Built Python APIs with PostgreSQL."]
    assert "Kubernetes" not in parsed["resume_keywords"] and "quality_report" not in parsed
    assert "evidence_ids" not in parsed and grounding_is_valid(original, parsed)
    schema = application_draft_schema(original)
    assert schema["additionalProperties"] is False
    assert schema["properties"]["evidence_ids"]["items"]["enum"]
    assert assess_application_quality(original, parsed)["disposition"] == "checks_passed"


@pytest.mark.parametrize("change", [
    {"evidence_ids": ["e_invented"]}, {"resume_keyword_ids": ["k_invented"]},
    {"evidence_ids": []},
])
def test_unknown_or_missing_selections_fail_closed_but_can_be_preserved_for_one_repair(change):
    original = context()
    response = wire(original, **change)
    with pytest.raises(ValueError, match="grounding IDs"):
        parse_application_draft(response, original)
    review = parse_application_draft(response, original, preserve_invalid_grounding=True)
    assert review["cover_letter"] == response["cover_letter"]
    assert review["evidence"] == [] and review["resume_keywords"] == []
    assert review["grounding"]["valid"] is False
    report = assess_application_quality(original, review)
    assert {"resume_grounding_invalid", "evidence_missing"} <= codes(report)


def test_duplicate_stale_or_mutated_ids_and_rendered_text_cannot_pass_final_review():
    original = context()
    response = wire(original)
    response["evidence_ids"] *= 2
    with pytest.raises(ValueError, match="grounding IDs"):
        parse_application_draft(response, original)
    response = wire(original)
    changed = context(resume_text=original["resume_text"] + "\nUpdated résumé.")
    with pytest.raises(ValueError, match="grounding IDs"):
        parse_application_draft(response, changed)
    parsed = parse_application_draft(response, original)
    parsed["quality_report"] = assess_application_quality(original, parsed)
    assert "do not match the current source" in application_quality_blocker(changed, parsed)
    parsed["evidence"] = ["PostgreSQL"]  # Literal alone does not match the issued selection.
    assert "resume_grounding_invalid" in codes(assess_application_quality(original, parsed))


def test_final_grounding_check_does_not_require_generation_only_profile_fields():
    original = context(skills=["latency", "Python"])
    parsed = parse_application_draft(wire(original), original)
    assert "latency" in parsed["resume_keywords"]
    final_context = {"resume_text": original["resume_text"], "description": "Changed posting text."}
    assert grounding_is_valid(final_context, parsed)


def test_prompt_uses_choices_without_duplicate_resume_and_bounded_correction_data():
    original = context()
    message = application_draft_messages(original)[1]["content"]
    assert original["resume_text"] not in message
    assert "synthetic@example.invalid" not in message
    assert "resume_keyword_ids" in message and "short, exact quotation" in message
    parsed = parse_application_draft(wire(original), original)
    parsed["quality_report"] = {"findings": [{"code": "unsupported_tenure_claim"}]}
    corrected = application_draft_messages(original, correction=parsed)[1]["content"]
    assert "ONE CORRECTIVE ATTEMPT" in corrected and "unsupported_tenure_claim" in corrected
    assert "quality_report" not in corrected  # Model is never asked to authorize its own copy.


def test_local_generation_passes_finite_schema_and_accounts_for_usage(monkeypatch):
    original = context()
    response = {"message": {"content": json.dumps(wire(original))},
                "prompt_eval_count": 30, "eval_count": 40}
    requests = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _limit):
            return json.dumps(response).encode()

    class Opener:
        def open(self, request, timeout):
            requests.append(json.loads(request.data))
            assert timeout == 180
            return Response()

    monkeypatch.setattr("app.career.build_opener", lambda: Opener())
    parsed, usage = generate_application_draft_with_usage(original, "synthetic:local")
    assert grounding_is_valid(original, parsed)
    assert requests[0]["format"] == application_draft_transport_schema(original)
    assert '"maxLength": 6000' in requests[0]["messages"][1]["content"]
    assert usage == {"prompt_tokens": 30, "completion_tokens": 40, "total_tokens": 70}


def test_local_transport_schema_avoids_large_grammar_expansion_without_losing_finite_ids():
    original = context()
    strict = application_draft_schema(original)
    transport = application_draft_transport_schema(original)
    assert strict["properties"]["cover_letter"]["maxLength"] == 6000
    assert strict["properties"]["fit_summary"]["maxLength"] == 2000
    assert strict["properties"]["evidence_ids"]["uniqueItems"] is True

    def check_grammar_subset(value):
        if isinstance(value, dict):
            assert not ({"minLength", "maxLength", "uniqueItems"} & value.keys())
            for item in value.values():
                check_grammar_subset(item)
        elif isinstance(value, list):
            for item in value:
                check_grammar_subset(item)

    check_grammar_subset(transport)
    assert transport["required"] == strict["required"]
    assert transport["additionalProperties"] is False
    for name in ("evidence_ids", "resume_keyword_ids"):
        assert transport["properties"][name]["items"]["enum"] == (
            strict["properties"][name]["items"]["enum"]
        )
        assert transport["properties"][name]["maxItems"] == (
            strict["properties"][name]["maxItems"]
        )
    # Transport filtering must never mutate the full prompt/server contract.
    assert strict == application_draft_schema(original)


@pytest.mark.parametrize("change", [
    {"fit_summary": "x" * 2001}, {"cover_letter": "x" * 6001},
    {"honest_gaps": ["x" * 501]}, {"fit_summary": ""},
])
def test_server_still_rejects_bounds_not_expressed_in_local_grammar(change):
    original = context()
    with pytest.raises(ValueError):
        parse_application_draft(wire(original, **change), original)

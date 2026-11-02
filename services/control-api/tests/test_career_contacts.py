from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.action_store import ActionPreparationError, SideEffectGuardError, guard_email_suppression
from app.application_browser import canonical_hash
from app.career_application_quality import assess_application_quality
from app.career_autopilot import opportunity_hash, profile_hash, target_key
from app.career_contact_models import CareerContactCreate, CareerContactEmailPlan
from app.career_contact_store import CareerContactStore
from app.career_contacts import (
    contact_scope_error,
    contact_snapshot,
    email_content_error,
    guard_career_contact_action,
    sender_identity_error,
)

NOW = datetime(2026, 11, 2, 12, tzinfo=UTC)


def material():
    profile_id, opportunity_id, contact_id, action_id, draft_id = [uuid4() for _ in range(5)]
    profile = {
        "id": profile_id, "candidate_name": "Synthetic Candidate",
        "resume_text": "Built Python APIs with PostgreSQL and Docker.",
        "application_identity": {"email": "candidate@example.test"},
        "desired_titles": ["Software Engineer"], "skills": ["Python", "PostgreSQL", "Docker"],
        "required_keywords": [], "excluded_keywords": ["Senior"], "locations": ["India"],
        "remote_only": False, "employment_types": ["FullTime"], "source_config": {},
        "max_age_hours": 72, "min_score": 75, "active": True,
    }
    opportunity = {
        "id": opportunity_id, "profile_id": profile_id, "company": "Synthetic Labs",
        "title": "Software Engineer", "description": "Build Python, PostgreSQL and Docker APIs.",
        "location": "India", "remote": False, "employment_type": "FullTime",
        "source": "ashby", "source_url": "https://jobs.ashbyhq.com/example/job",
        "apply_url": "https://jobs.ashbyhq.com/example/job", "published_at_basis": "published",
        "published_at": NOW - timedelta(hours=1), "status": "new", "score": 100,
    }
    contact = {
        "id": contact_id, "profile_id": profile_id, "opportunity_id": opportunity_id,
        "email": "hiring@example.test", "kind": "hiring",
        "source_url": "https://example.test/careers",
        "evidence_quote": "For engineering careers, email hiring@example.test.",
        "basis_note": "Employer careers page explicitly requests engineering applications.",
        "reviewed_by": "operator:test", "reviewed_at": NOW - timedelta(minutes=1),
        "expires_at": NOW + timedelta(hours=24), "revoked_at": None,
        "profile_hash": profile_hash(profile), "opportunity_hash": opportunity_hash(opportunity),
    }
    content = {
        "fit_summary": "Relevant Python API projects.",
        "evidence": ["Built Python APIs with PostgreSQL and Docker."],
        "honest_gaps": [], "resume_keywords": ["Python", "PostgreSQL"],
        "cover_letter": "I built Python APIs with PostgreSQL and Docker. I would welcome "
                        "the opportunity to discuss your engineering role and learn about "
                        "the team's current API requirements.",
    }
    content["quality_report"] = assess_application_quality(
        {**opportunity, "resume_text": profile["resume_text"]}, content,
    )
    draft = {"id": draft_id, "content": content}
    action = {
        "id": action_id, "action_type": "communications.email_send",
        "opportunity_id": opportunity_id,
        "private_context": {
            "sender": "candidate@example.test", "recipient": contact["email"],
            "career_contact": {"contact_id": str(contact_id), "snapshot": contact_snapshot(contact),
                               "draft_id": str(draft_id), "draft_sha256": canonical_hash(content)},
        },
    }
    ledger = {"contact_id": contact_id, "profile_id": profile_id,
              "opportunity_id": opportunity_id, "recipient": contact["email"],
              "target_key": target_key(opportunity["apply_url"])}
    return profile, opportunity, contact, draft, action, ledger


def review(**changes):
    return CareerContactCreate(**{
        "email": "hiring@example.test", "kind": "hiring",
        "source_url": "https://example.test/careers",
        "evidence_quote": "Apply to engineering careers: hiring@example.test.",
        "basis_note": "Employer primary careers page invites relevant applications.",
        "reviewed_by": "operator:test", "attested_primary_source": True, **changes,
    })


@pytest.mark.parametrize("changes", [
    {"attested_primary_source": False}, {"attested_primary_source": None},
    {"validity_hours": 73}, {"email": "inferred@example.test"},
    {"email": "support@example.test"}, {"kind": "sales"},
    {"source_url": "http://example.test/careers"},
    {"source_url": "https://user:pass@example.test/careers"},
    {"source_url": "https://127.0.0.1/careers"},
    {"source_url": "https://example.test/careers#evidence"},
])
def test_contact_review_requires_bounded_explicit_primary_source_attestation(changes):
    with pytest.raises(ValidationError):
        review(**changes)


def test_exact_published_address_is_normalized_but_never_guessed():
    assert review(email="HIRING@example.test").email == "hiring@example.test"
    with pytest.raises(ValidationError):
        review(evidence_quote="Write to nothiring@example.test for applications.")


def test_contact_scope_uses_current_fit_strict_freshness_and_current_resume():
    profile, opportunity, contact, *_ = material()
    assert contact_scope_error(contact, profile, opportunity, NOW) is None
    for changes in ({"published_at": NOW - timedelta(hours=73)},
                    {"published_at_basis": "updated"}, {"status": "applied"},
                    {"description": "Unrelated role with no matching engineering skills."}):
        changed = {**opportunity, **changes}
        # Simulate a fresh review: old stored score=100 cannot grant current fit.
        current = {**contact, "opportunity_hash": opportunity_hash(changed)}
        assert contact_scope_error(current, profile, changed, NOW)
    assert contact_scope_error(contact, {**profile, "resume_text": "Changed"}, opportunity, NOW)
    assert contact_scope_error({**contact, "revoked_at": NOW}, profile, opportunity, NOW)
    assert contact_scope_error({**contact, "expires_at": NOW}, profile, opportunity, NOW)


def test_profile_sender_must_match_chosen_application_identity():
    profile, *_ = material()
    assert sender_identity_error(profile, "candidate@example.test") is None
    assert sender_identity_error(profile, "creator@example.test")
    assert sender_identity_error(profile, "")


class Connection:
    def __init__(self, items, *, now=NOW, suppressed=False, duplicate=False):
        self.profile, self.opportunity, self.contact, self.draft, self.action, self.ledger = items
        self.now, self.suppressed, self.statements = now, suppressed, []
        self.duplicate = duplicate

    def execute(self, query, params=()):
        self.statements.append((query, params))
        value = None
        if "clock_timestamp()" in query:
            value = {"now": self.now}
        elif "FROM career_contact_actions WHERE action_id" in query:
            value = self.ledger
        elif "FROM career_contacts" in query:
            value = self.contact
        elif "FROM career_profiles" in query:
            value = self.profile
        elif "FROM job_opportunities" in query:
            value = self.opportunity
        elif "FROM job_application_drafts" in query:
            value = self.draft
        elif "FROM creator_contact_suppressions" in query:
            value = {"exists": 1} if self.suppressed else None
        elif "FROM external_actions" in query:
            value = {"id": uuid4(), "apply_url": self.opportunity["apply_url"]} \
                if self.duplicate else None
        return Mock(fetchone=Mock(return_value=value),
                    fetchall=Mock(return_value=[value] if value else []))

    def commit(self):
        pass


@pytest.mark.parametrize("acquire_locks", [True, False])
@pytest.mark.parametrize("mutation,expected", [
    ("revoke", "revoked"), ("source", "packet changed"), ("recipient", "packet changed"),
    ("sender", "SMTP sender"), ("resume", "Profile changed"),
    ("draft", "draft changed"), ("missing_ledger", "durable ledger"),
    ("expiry_after_wait", "expired"), ("job", "Job details changed"),
    ("wrong_profile", "packet changed"), ("wrong_target", "packet changed"),
    ("attachment", "no attachments"),
])
def test_final_contact_fence_rechecks_revocation_material_and_time_after_row_locks(
    mutation, expected, acquire_locks,
):
    connection = Connection(material())
    guard_career_contact_action(connection, connection.action, acquire_locks=acquire_locks)
    statements = [query.upper() for query, _ in connection.statements]
    if acquire_locks:
        assert any("FOR SHARE" in query for query in statements)
    else:
        assert all("FOR SHARE" not in query and "FOR UPDATE" not in query
                   and "PG_ADVISORY" not in query for query in statements)
    if mutation == "revoke":
        connection.contact["revoked_at"] = NOW
    elif mutation == "source":
        connection.contact["source_url"] = "https://other.test/careers"
    elif mutation == "recipient":
        connection.action["private_context"]["recipient"] = "other@example.test"
    elif mutation == "sender":
        connection.action["private_context"]["sender"] = "creator@example.test"
    elif mutation == "resume":
        # Keep old evidence present so the profile-snapshot fence itself is exercised.
        connection.profile["resume_text"] += " Additional truthful detail."
    elif mutation == "draft":
        connection.draft["content"]["cover_letter"] += " Another sentence."
    elif mutation == "missing_ledger":
        connection.ledger = None
    elif mutation == "expiry_after_wait":
        connection.now += timedelta(hours=25)
    elif mutation == "job":
        connection.opportunity["description"] += " New eligibility restriction."
    elif mutation == "wrong_profile":
        connection.opportunity["profile_id"] = uuid4()
    elif mutation == "wrong_target":
        connection.ledger["target_key"] = "unrelated-canonical-target"
    elif mutation == "attachment":
        connection.action["private_context"]["body"] = "Please find my attached resume."
    with pytest.raises(SideEffectGuardError, match=expected):
        guard_career_contact_action(connection, connection.action, acquire_locks=acquire_locks)
    if not acquire_locks:
        assert all("FOR SHARE" not in query.upper() and "FOR UPDATE" not in query.upper()
                   and "PG_ADVISORY" not in query.upper() for query, _ in connection.statements)


def test_ordinary_and_career_email_both_honor_global_durable_suppression():
    connection = Connection(material(), suppressed=True)
    for action in (connection.action, {"action_type": "communications.email_send",
                                      "private_context": {"recipient": "HIRING@example.test"}}):
        with pytest.raises(SideEffectGuardError, match="durably suppressed"):
            guard_email_suppression(connection, action)
    assert any(params == ("creator-email:hiring@example.test",)
               for _, params in connection.statements)
    # Browser applications do not acquire SMTP recipient authority.
    guard_email_suppression(connection, {"action_type": "career.application_submit"})


def test_career_delivery_is_deduplicated_across_exact_manual_and_play_email_paths():
    connection = Connection(material(), duplicate=True)
    with pytest.raises(SideEffectGuardError, match="already has a delivery"):
        guard_email_suppression(connection, connection.action)
    statements = [sql for sql, _ in connection.statements]
    assert "pg_advisory_xact_lock" in statements[0]
    assert "'executing', 'succeeded', 'ambiguous'" in statements[-1]


@pytest.mark.parametrize("body", ["Please find my CV attached.", "I am attaching my resume.",
                                  "My résumé is enclosed."])
def test_email_without_attachments_cannot_claim_an_attachment(body):
    assert email_content_error(body)
    assert email_content_error("My Python projects are described below.") is None


def test_career_email_acceptance_marks_application_using_either_governed_ledger():
    connection = Connection(material())
    action_id, task_id = uuid4(), uuid4()

    def execute(sql, params=()):
        connection.statements.append((sql, params))
        if "UPDATE external_actions" in sql:
            value = {"id": action_id, "action_type": "communications.email_send",
                     "opportunity_id": connection.opportunity["id"], "private_context": {}}
        elif "UPDATE side_effect_receipts" in sql:
            value = {"task_id": task_id}
        else:
            value = None
        return Mock(fetchone=Mock(return_value=value))

    connection.execute = execute
    store = CareerContactStore("not-used")

    @contextmanager
    def connect():
        yield connection

    store.connect = connect
    store.complete_side_effect(task_id, "synthetic-fingerprint", "smtp-reference")
    sql, params = next((sql, params) for sql, params in connection.statements
                       if "UPDATE job_opportunities" in sql)
    assert "career_autopilot_actions" in sql and "career_contact_actions" in sql
    assert params == (connection.opportunity["id"], action_id, action_id)


def test_contact_email_is_an_exact_pending_action_and_has_a_durable_dedupe_ledger():
    connection = Connection(material())
    store = CareerContactStore("not-used")

    @contextmanager
    def connect():
        yield connection

    store.connect = connect
    store._create_external_action = Mock(return_value={"id": uuid4(), "status": "pending_approval"})
    action = store.prepare_contact_email(connection.contact["id"],
                                        CareerContactEmailPlan(actor="operator:test"),
                                        sender="candidate@example.test")
    assert action["status"] == "pending_approval"
    frozen = store._create_external_action.call_args.kwargs
    assert frozen["action_type"] == "communications.email_send"
    assert (frozen["private_context"]["career_contact"]["snapshot"]
            == contact_snapshot(connection.contact))
    assert "Application reference: HERMES-" in frozen["public_context"]["body"]
    assert any("INSERT INTO career_contact_actions" in sql for sql, _ in connection.statements)
    with pytest.raises(ActionPreparationError, match="SMTP sender"):
        store.prepare_contact_email(connection.contact["id"],
                                    CareerContactEmailPlan(actor="operator:test"),
                                    sender="creator@example.test")

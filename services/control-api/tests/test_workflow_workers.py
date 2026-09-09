from datetime import UTC, datetime
from unittest.mock import Mock
from uuid import uuid4

import pytest

from app import action_worker, job_worker
from app.action_store import ActionStore
from app.marketing_store import MarketingStore


def _workflow_payload(payload: dict, managed: bool | None) -> dict:
    return payload if managed is None else {**payload, "workflow_managed": managed}


@pytest.mark.parametrize("managed", [None, False, True])
def test_search_preserves_results_without_creating_unplanned_workflow_children(
    monkeypatch: pytest.MonkeyPatch, managed: bool | None
) -> None:
    profile_id, opportunity_id = uuid4(), uuid4()
    database = Mock(spec=MarketingStore)
    database.get_profile.return_value = {
        "source_config": {"ashby_boards": ["synthetic-board"]},
        "desired_titles": ["Software Engineer"],
        "skills": ["Python", "PostgreSQL"],
        "required_keywords": [],
        "excluded_keywords": [],
        "locations": ["Remote"],
        "remote_only": True,
        "employment_types": ["FullTime"],
        "max_age_hours": 72,
        "min_score": 40,
        "resume_text": "Synthetic Python and PostgreSQL experience.",
    }
    discovered = {
        "source": "ashby",
        "source_key": "synthetic-role",
        "company": "Synthetic Company",
        "title": "Software Engineer",
        "location": "Remote",
        "description": "Develop Python services backed by PostgreSQL.",
        "remote": True,
        "employment_type": "FullTime",
        "source_url": "https://jobs.ashbyhq.com/synthetic-board/synthetic-role",
        "apply_url": "https://jobs.ashbyhq.com/synthetic-board/synthetic-role/apply",
        "published_at": datetime.now(UTC),
    }
    fetch = Mock(return_value=[discovered])
    monkeypatch.setattr(job_worker, "fetch_ashby", fetch)
    database.save_opportunities.return_value = {
        "new": 1, "updated": 0, "auto_prepare_ids": [opportunity_id],
    }

    output = job_worker.execute_career_task(
        {
            "id": uuid4(),
            "kind": "career.search",
            "payload": _workflow_payload({"profile_id": str(profile_id)}, managed),
        },
        database,
    )

    fetch.assert_called_once_with("synthetic-board")
    database.save_opportunities.assert_called_once()
    assert output["matched"] == 1
    assert output["new"] == 1
    if managed:
        database.create_task.assert_not_called()
        assert output["auto_prepared"] == 0
    else:
        children = [call.args[0] for call in database.create_task.call_args_list]
        assert [child.kind for child in children] == [
            "career.application_draft", "career.application_preflight",
        ]
        assert all(child.payload["opportunity_id"] == str(opportunity_id) for child in children)
        assert output["auto_prepared"] == 1


@pytest.mark.parametrize("managed", [None, False, True])
def test_draft_saves_model_result_without_preparing_unplanned_workflow_action(
    monkeypatch: pytest.MonkeyPatch, managed: bool | None
) -> None:
    profile_id, opportunity_id, task_id = uuid4(), uuid4(), uuid4()
    database = Mock(spec=MarketingStore)
    context = {"resume_text": "Synthetic experience", "title": "Software Engineer"}
    content = {
        "fit_summary": "Synthetic fit", "evidence": ["Python"], "honest_gaps": [],
        "resume_keywords": ["Python"], "cover_letter": "Synthetic draft.",
    }
    database.get_draft_context.return_value = context
    database.start_inference_invocation.return_value = uuid4()
    database.try_create_automatic_application_action.return_value = {"id": uuid4()}
    generate = Mock(return_value=(content, {
        "prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30,
    }))
    monkeypatch.setattr(job_worker, "openrouter_client", None)
    monkeypatch.setattr(job_worker, "generate_application_draft_with_usage", generate)

    output = job_worker.execute_career_task(
        {
            "id": task_id,
            "kind": "career.application_draft",
            "payload": _workflow_payload({
                "profile_id": str(profile_id), "opportunity_id": str(opportunity_id),
            }, managed),
        },
        database,
    )

    generate.assert_called_once_with(context, job_worker.settings.local_model)
    database.save_application_draft.assert_called_once_with(
        opportunity_id=opportunity_id, profile_id=profile_id, task_id=task_id,
        model=job_worker.settings.local_model, content=content,
    )
    assert output["draft_created"] is True
    assert output["automatic_approval_task_created"] is (not managed)
    if managed:
        database.try_create_automatic_application_action.assert_not_called()
    else:
        database.try_create_automatic_application_action.assert_called_once_with(opportunity_id)


@pytest.mark.parametrize("managed", [None, False, True])
def test_preflight_saves_inspection_without_preparing_unplanned_workflow_action(
    monkeypatch: pytest.MonkeyPatch, managed: bool | None
) -> None:
    opportunity_id, task_id = uuid4(), uuid4()
    database = Mock(spec=ActionStore)
    apply_url = "https://jobs.ashbyhq.com/synthetic-board/synthetic-role/apply"
    database.get_opportunity.return_value = {"apply_url": apply_url}
    database.try_create_automatic_application_action.return_value = {"id": uuid4()}
    result = {"fields": [{"key": "name:0", "label": "Name"}], "blocked_reason": None}
    inspect = Mock(return_value=result)
    monkeypatch.setattr(action_worker, "inspect_application_form", inspect)

    output = action_worker.execute_action_task(
        {
            "id": task_id,
            "kind": "career.application_preflight",
            "payload": _workflow_payload({"opportunity_id": str(opportunity_id)}, managed),
        },
        database,
        action_worker.settings,
    )

    inspect.assert_called_once_with(apply_url, action_worker.settings.environment)
    database.save_preflight.assert_called_once_with(
        opportunity_id=opportunity_id, task_id=task_id, result=result,
    )
    assert output["field_count"] == 1
    assert output["automatic_approval_task_created"] is (not managed)
    if managed:
        database.try_create_automatic_application_action.assert_not_called()
    else:
        database.try_create_automatic_application_action.assert_called_once_with(opportunity_id)

"""Safe, historical operator test evidence and actionable feature prerequisites."""

from datetime import UTC, datetime, timedelta
from typing import Literal, Self
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator

from app.auth import require_api_token, require_bearer_token
from app.store import Database

CheckId = Literal[
    "core",
    "restore",
    "environment",
    "omniroute",
    "openrouter",
    "local_model",
    "hermes",
    "career",
    "side_effects",
    "creator_outreach",
    "planning",
    "scheduler",
    "youtube",
]


class FeatureCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: CheckId
    status: Literal["passed", "failed", "skipped"]
    duration_seconds: float = Field(ge=0, le=172800, allow_inf_nan=False)
    reason_code: (
        Literal[
            "NOT_SELECTED",
            "NOT_IMPLEMENTED",
            "CHECK_PASSED",
            "CHECK_FAILED",
            "NOT_CONFIGURED",
            "REUSED_READINESS_PASSED",
            "REUSED_READINESS_FAILED",
            "REUSED_READINESS_SKIPPED",
        ]
        | None
    ) = None


class FeatureSignals(BaseModel):
    model_config = ConfigDict(extra="forbid")
    core_online: StrictBool
    research_worker_online: StrictBool
    action_worker_online: StrictBool
    ollama_online: StrictBool
    hermes_online: StrictBool
    omniroute_online: StrictBool
    openrouter_enabled: StrictBool
    youtube_configured: StrictBool
    mail_transport: Literal["disabled", "mailpit", "smtp"]
    external_smtp_configured: StrictBool
    local_model_cached: StrictBool


class FeatureReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: UUID
    git_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    working_tree_dirty: StrictBool
    started_at: datetime
    completed_at: datetime
    checks: list[FeatureCheck] = Field(min_length=1, max_length=13)
    signals: FeatureSignals

    @model_validator(mode="after")
    def validate_report(self) -> Self:
        if self.started_at.tzinfo is None or self.completed_at.tzinfo is None:
            raise ValueError("Test timestamps must include a timezone")
        if not self.started_at <= self.completed_at <= datetime.now(UTC) + timedelta(minutes=5):
            raise ValueError("Test timestamps must be ordered and cannot be in the future")
        if self.completed_at - self.started_at > timedelta(days=2):
            raise ValueError("A feature test run cannot span more than two days")
        if len({check.id for check in self.checks}) != len(self.checks):
            raise ValueError("Each check can appear only once")
        return self


def feature_catalog(report: FeatureReport | None, counts: dict, *, now=None) -> dict:
    now = now or datetime.now(UTC)
    stale = report is None or now - report.completed_at > timedelta(hours=24)
    checks = {check.id: check for check in report.checks} if report else {}
    signals = report.signals.model_dump() if report else {}
    features = []

    def add(
        key,
        title,
        summary,
        check_id,
        requirements,
        view,
        label,
        *,
        action=None,
        scope="Local end-to-end check passed.",
        implemented=True,
        allow_verified=True,
    ):
        check = checks.get(check_id)
        verified = bool(check and check.status == "passed" and not stale)
        ready = all(met for _, met in requirements)
        status = (
            "unavailable"
            if not implemented
            else "needs_setup"
            if not ready
            else "verified"
            if verified and allow_verified
            else "configured"
        )
        if not implemented:
            reason = "Roadmap capability; no operational integration is implemented."
        elif not ready:
            reason = "Next: " + "; ".join(label for label, met in requirements if not met) + "."
        elif verified and allow_verified:
            reason = scope + " Evidence describes the recorded run, not current availability."
        elif check and check.status == "failed":
            reason = "The recorded check failed. Run the feature test again after resolving setup."
        elif report and stale:
            reason = "Recorded evidence is over 24 hours old. Run feature-test.ps1 to check again."
        else:
            reason = "Setup is present; this feature still needs its own end-to-end proof."
        evidence = None
        if check and check.status == "passed":
            evidence = {
                "run_id": str(report.run_id),
                "check_id": check.id,
                "completed_at": report.completed_at.isoformat(),
            }
        features.append(
            {
                "id": key,
                "title": title,
                "summary": summary,
                "status": status,
                "reason": reason,
                "requirements": [{"label": label, "met": bool(met)} for label, met in requirements],
                "evidence": evidence,
                "next_action": {
                    "label": label,
                    "view": view,
                    **({"action": action} if action else {}),
                },
            }
        )

    core = ("Core services checked online", signals.get("core_online", False))
    research = ("Research worker checked online", signals.get("research_worker_online", False))
    actions = ("Action worker checked online", signals.get("action_worker_online", False))
    profile = ("Create a career mission", counts.get("profiles", 0) > 0)
    resume = ("Add a résumé to a career mission", counts.get("resumes", 0) > 0)
    campaign = ("Create a creator campaign", counts.get("campaigns", 0) > 0)
    hosted_ready = bool(
        signals.get("openrouter_enabled")
        and checks.get("openrouter")
        and checks["openrouter"].status == "passed"
    )
    local_ready = bool(
        signals.get("ollama_online")
        and signals.get("local_model_cached")
        and checks.get("local_model")
        and checks["local_model"].status == "passed"
    )
    model = ("Check a configured inference route", (hosted_ready or local_ready) and not stale)
    add(
        "tasks",
        "Tasks and approvals",
        "Track work, inspect results, cancel tasks, and review approvals.",
        "core",
        [core],
        "tasks",
        "Open task history",
    )
    add(
        "workflows",
        "Durable workflows",
        "Run bounded steps with dependencies, deadlines, and result checks.",
        "core",
        [core],
        "workflows",
        "Choose a recipe",
    )
    add(
        "planning",
        "Goal proposals",
        "Turn a goal and selected context into a plan you review before starting.",
        "planning",
        [research],
        "goals",
        "Try a proposal",
        action="goal-demo",
        scope=("Proposal isolation, reviewed adoption, and workflow execution passed; "
               "demo needs no model."),
    )
    add(
        "career_search",
        "Job discovery",
        "Find and rank fresh jobs using your mission criteria.",
        "career",
        [research, profile],
        "missions",
        "Open career missions",
    )
    add(
        "application_drafts",
        "Application drafts",
        "Prepare a grounded draft using your résumé and a selected job.",
        "career",
        [research, profile, resume, model],
        "opportunities",
        "Review job matches",
    )
    add(
        "application_preflight",
        "Application form inspection",
        "Inspect supported forms before preparing a submission.",
        "side_effects",
        [actions, profile],
        "opportunities",
        "Inspect a job",
        scope="Local fixture inspection passed; each real ATS still needs compatibility checks.",
    )
    add(
        "application_submit",
        "Reviewed applications",
        "Approve the exact form and identity snapshot before submitting.",
        "side_effects",
        [actions, profile],
        "approvals",
        "Review approvals",
        scope=("Local fixture approval and submission passed; "
               "this does not prove compatibility with every ATS."),
    )
    add(
        "email_test",
        "Local email delivery",
        "Exercise email approval and delivery into the local Mailpit inbox.",
        "side_effects",
        [
            actions,
            ("Select the local Mailpit transport", signals.get("mail_transport") == "mailpit"),
        ],
        "approvals",
        "Open approvals",
        scope="Approval and delivery to local Mailpit passed.",
    )
    add(
        "creator_campaigns",
        "Creator outreach preparation",
        "Build promotion kits, qualify prospects, and record outcomes.",
        "creator_outreach",
        [campaign],
        "campaigns",
        "Open campaigns",
        scope="Campaign, qualification, reviewed local email, and outcome feedback passed.",
    )
    add(
        "creator_discovery",
        "YouTube creator discovery",
        "Research YouTube fit and published business-contact candidates; review before outreach.",
        "youtube",
        [
            research,
            campaign,
            ("Configure the YouTube API key", signals.get("youtube_configured", False)),
        ],
        "campaigns",
        "Open creator campaigns",
        scope="A bounded live YouTube discovery request passed.",
    )
    add(
        "external_email",
        "External email delivery",
        "Send an approved email through your own configured SMTP service.",
        None,
        [
            actions,
            ("Configure external SMTP", signals.get("external_smtp_configured", False)),
            ("Select SMTP transport", signals.get("mail_transport") == "smtp"),
        ],
        "settings",
        "Read email setup",
        allow_verified=False,
    )
    add(
        "inference",
        "Model routing",
        "Use hosted free routing with a local Qwen fallback and a usage ledger.",
        "openrouter" if signals.get("openrouter_enabled") else "local_model",
        [model],
        "settings",
        "Inspect inference status",
    )
    add(
        "backups",
        "Backup restoration",
        "Restore a backup into a disposable database and compare it with the source.",
        "restore",
        [],
        "settings",
        "Open operations help",
    )
    add(
        "future_integrations",
        "Additional integrations",
        "General MCP tools, Telegram, and autonomous coding remain future work.",
        None,
        [],
        "settings",
        "Read the project guide",
        implemented=False,
    )
    stats = {
        status: sum(item["status"] == status for item in features)
        for status in ("verified", "configured", "needs_setup", "unavailable")
    }
    return {
        "features": features,
        "stats": stats,
        "last_report": {
            **report.model_dump(mode="json", exclude={"signals"}),
            "stale": stale,
        }
        if report
        else None,
    }


class ReadinessStore(Database):
    def record_report(self, report: FeatureReport) -> dict:
        document = report.model_dump(mode="json")
        with self.connect() as connection:
            inserted = connection.execute(
                """INSERT INTO feature_test_runs
                   (id, git_commit, working_tree_dirty, started_at, completed_at, report)
                   VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (id) DO NOTHING RETURNING id""",
                (
                    report.run_id,
                    report.git_commit,
                    report.working_tree_dirty,
                    report.started_at,
                    report.completed_at,
                    Jsonb(document),
                ),
            ).fetchone()
            if not inserted:
                existing = connection.execute(
                    "SELECT report FROM feature_test_runs WHERE id = %s",
                    (report.run_id,),
                ).fetchone()["report"]
                if existing != document:
                    raise ValueError("This run ID already records different evidence")
            else:
                self._append_audit(
                    connection,
                    correlation_id=uuid4(),
                    task_id=None,
                    actor_type="operator",
                    actor_id="local-feature-test",
                    action="readiness.report_recorded",
                    risk_level="low",
                    approval_status="not_applicable",
                    execution_status="recorded",
                    input_metadata={"run_id": str(report.run_id)},
                    result_metadata={"checks": len(report.checks)},
                )
        return {"run_id": str(report.run_id), "recorded": True}

    def features(self) -> dict:
        with self.connect() as connection:
            latest = connection.execute(
                "SELECT report FROM feature_test_runs ORDER BY completed_at DESC LIMIT 1",
            ).fetchone()
            counts = connection.execute(
                """SELECT (SELECT count(*) FROM career_profiles) AS profiles,
                   (SELECT count(*) FROM career_profiles
                    WHERE length(trim(resume_text)) > 0) AS resumes,
                   (SELECT count(*) FROM marketing_campaigns) AS campaigns""",
            ).fetchone()
        return feature_catalog(
            FeatureReport.model_validate(latest["report"]) if latest else None, counts
        )


router = APIRouter(prefix="/v1/readiness")


@router.get("/features", dependencies=[Depends(require_api_token)])
def readiness_features(request: Request):
    return request.app.state.readiness.features()


@router.post("/reports", dependencies=[Depends(require_bearer_token)])
def readiness_report(request: Request, payload: FeatureReport):
    try:
        return request.app.state.readiness.record_report(payload)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

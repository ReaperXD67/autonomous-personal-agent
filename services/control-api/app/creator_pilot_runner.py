from uuid import UUID

from app.creator_pilot import KIND, MAX_CREATORS, MAX_UPLOADS, rank_prospect, shortlist_order
from app.marketing import YouTubeRequestLimitError, fetch_youtube_prospect
from app.store import InvalidTaskStateError
from app.worker import TaskInterruptedError


def execute_creator_pilot(task, store, settings, *, interrupt=None):
    task_id, lease_id = UUID(str(task["id"])), UUID(str(task["lease_id"]))

    def checkpoint(prospect_id=None):
        if interrupt is not None and interrupt.is_set():
            raise TaskInterruptedError("Pilot research was interrupted")
        return store.pilot_context(task_id, lease_id, prospect_id)

    issued, _, _ = checkpoint()
    ids = issued["payload"]["prospect_ids"]
    if not 1 <= len(ids) <= MAX_CREATORS:
        raise ValueError("Pilot reservation exceeds the bounded creator limit")
    ranked, failed = [], 0
    quota_limited = False
    for identity in ids:
        prospect_id = UUID(identity)
        _, campaign, prospect = checkpoint(prospect_id)
        error = quota_limited
        if not quota_limited:
            try:
                research = fetch_youtube_prospect(
                    settings.youtube_api_key, campaign, prospect, include_recent_activity=True,
                    checkpoint=lambda identity=prospect_id: checkpoint(identity),
                )
            except YouTubeRequestLimitError:
                quota_limited = error = True
            except (InvalidTaskStateError, TaskInterruptedError):
                raise
            except (RuntimeError, ValueError):
                error = True
            if not error:
                checkpoint(prospect_id)
                campaign, prospect = store.save_pilot_research(
                    task_id, lease_id, prospect_id, research,
                )
        if error:
            failed += 1
        ranked.append(rank_prospect(campaign, prospect, error=error))
    checkpoint()
    ranked.sort(key=shortlist_order)
    return {
        "handler": KIND, "campaign_id": issued["payload"]["campaign_id"],
        "requested_limit": issued["payload"]["requested_limit"],
        "researched": len(ids) - failed, "failed": failed,
        "selected_count": sum(row["status"] == "selected" for row in ranked),
        "requires_contact_review_count": sum(row["status"] == "needs_review" for row in ranked),
        "ranked": ranked,
        "limits": {"max_creators": MAX_CREATORS, "max_uploads_per_creator": MAX_UPLOADS,
                   "model_requests": 0, "contact_authorizations": 0, "messages_sent": 0},
        "caveat": "API metadata and declared language only; no watched-video, audience-region "
                  "or collaboration-interest claims. "
                  "A shortlist grants no contact or send authority.",
    }

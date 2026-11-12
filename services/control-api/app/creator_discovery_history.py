"""Bulk-only preservation of known creator identities with durable history.

This is an evidence fence, never contact/sending authority or a recipient opt-out.
Explicit research keeps its separate existing invalidation and eligibility rules.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any
from uuid import UUID

from app.application_browser import canonical_hash
from app.creator_intelligence import EMAIL

IdentityKey = tuple[str, ...]


def _prospect_key(value: Any) -> set[IdentityKey]:
    try:
        return {("prospect", str(UUID(str(value))))}
    except (TypeError, ValueError, AttributeError):
        return set()


def _email_key(value: Any) -> set[IdentityKey]:
    if not isinstance(value, str):
        return set()
    value = value.strip().casefold()
    return {("email", value)} if EMAIL.fullmatch(value) else set()


def identity_keys(prospect: Any) -> set[IdentityKey]:
    # Lazy reuse avoids MarketingStore -> pilot-store -> MarketingStore import cycles.
    from app.creator_pilot_store import research_identity

    if not isinstance(prospect, dict):
        return set()
    prospect = dict(prospect)
    for field in ("platform", "external_id", "profile_url", "contact_email"):
        if not isinstance(prospect.get(field), str):
            prospect[field] = None
    intelligence = prospect.get("intelligence")
    intelligence = intelligence if isinstance(intelligence, dict) else {}
    candidates = intelligence.get("contact_candidates")
    candidates = candidates if isinstance(candidates, list) else []
    clean = {**prospect, "intelligence": {**intelligence, "contact_candidates": candidates}}
    keys = research_identity(clean)[3] | _prospect_key(prospect.get("id"))
    # Retained dated public observations are known aliases, not current permission.
    history = intelligence.get("contact_history")
    if isinstance(history, list):
        for item in history[:20]:
            if isinstance(item, dict):
                keys.update(_email_key(item.get("email")))
    return keys


def _snapshot_keys(snapshot: Any) -> set[IdentityKey]:
    if not isinstance(snapshot, dict):
        return set()
    keys: set[IdentityKey] = set()
    for field in ("contact", "research"):
        if isinstance(snapshot.get(field), dict):
            keys.update(identity_keys(snapshot[field]))
    return keys


class HistoryIndex:
    """Transaction-local connected known aliases; no names or guessed addresses."""

    def __init__(self, groups: Iterable[tuple[set[IdentityKey], bool]]):
        parent: dict[IdentityKey, IdentityKey] = {}
        frozen: set[IdentityKey] = set()

        def find(key):
            parent.setdefault(key, key)
            while parent[key] != key:
                parent[key] = parent[parent[key]]
                key = parent[key]
            return key

        for keys, preserved in groups:
            if not keys:
                continue
            first, *others = sorted(keys)
            find(first)
            for other in others:
                parent[find(other)] = find(first)
            if preserved:
                frozen.add(first)
        components: dict[IdentityKey, set[IdentityKey]] = {}
        for key in parent:
            components.setdefault(find(key), set()).add(key)
        self._components = {key: components[find(key)] for key in parent}
        self._frozen = {find(key) for key in frozen}
        self._roots = {key: find(key) for key in parent}
        self._groups = [(keys, root in self._frozen) for root, keys in components.items()]

    def with_observations(self, prospects) -> HistoryIndex:
        # A fresh address observed on a preserved canonical channel is known at
        # this save boundary. Propagate it across this batch without rewriting
        # the preserved source or claiming knowledge before provider metadata.
        return HistoryIndex([*self._groups,
                             *((identity_keys(row), False) for row in prospects)])

    def keys(self, prospect, existing=None) -> set[IdentityKey]:
        keys = identity_keys(prospect)
        if existing is not None:
            keys.update(identity_keys(existing))
        # Each component is already transitively closed across current/frozen rows.
        return keys | {alias for key in keys for alias in self._components.get(key, ())}

    def protected(self, prospect, existing=None) -> bool:
        return any(self._roots.get(key) in self._frozen for key in self.keys(prospect, existing))


def sender_lock_keys(keys: Iterable[IdentityKey]) -> set[str]:
    result = set()
    for key in keys:
        if key[0] in {"email", "profile"}:
            result.add(f"creator-{key[0]}:{key[1]}")
        elif key[0] == "channel":
            result.add(f"creator-platform:youtube:{key[1]}")
        elif key[0] == "creator":
            result.add(f"creator-platform:{key[1]}:{key[2]}")
    return result


def lock_history_writers(connection):
    # Match pilot -> draft-budget -> automation -> campaign/prospect -> sorted
    # sender locks. Never acquire budget/automation after a campaign or task row.
    connection.execute("SELECT pg_advisory_xact_lock(hashtext('creator-pilot-budget'))")
    connection.execute("SELECT pg_advisory_xact_lock(hashtext('creator-draft-budget'))")
    connection.execute("SELECT pg_advisory_xact_lock(hashtextextended('creator-automation',0))")


def _reservation_groups(row):
    payload = row["payload"]
    if not isinstance(payload, dict) or row["payload_hash"] != canonical_hash(payload):
        return []
    groups = []
    if row["kind"] == "marketing.creator_draft_batch":
        from app.creator_draft_batch_store import batch_items
        from app.store import InvalidTaskStateError

        try:
            items = batch_items(payload)
        except InvalidTaskStateError:
            return []
        groups.extend((_prospect_key(item["prospect_id"]), True) for item in items)
    elif row["kind"] == "marketing.creator_pilot":
        ids, profiles = payload.get("prospect_ids"), payload.get("profile_urls")
        if not isinstance(ids, list) or not 1 <= len(ids) <= 10 or not isinstance(profiles, dict):
            return []
        for value in ids:
            key = _prospect_key(value)
            if not key:
                return []
            profile = {"platform": "youtube", "profile_url": profiles.get(value)}
            groups.append((key | identity_keys(profile), True))
    return groups


def load_history(connection) -> HistoryIndex:
    """Read complete authoritative history; expiry/status never releases a bulk pin."""
    groups = []
    prospects = connection.execute(
        "SELECT id,platform,external_id,profile_url,contact_email,"
        "status,suppressed_at,intelligence "
        "FROM marketing_prospects",
    ).fetchall()
    for prospect in prospects:
        preserved = (prospect.get("suppressed_at") is not None
                     or prospect["status"] not in {"discovered", "qualified"})
        groups.append((identity_keys(prospect), preserved))

    for row in connection.execute(
        "SELECT prospect_id,input_snapshot FROM creator_email_drafts UNION ALL "
        "SELECT prospect_id,input_snapshot FROM creator_reply_drafts",
    ).fetchall():
        keys = _prospect_key(row["prospect_id"]) | _snapshot_keys(row["input_snapshot"])
        groups.append((keys, True))

    for row in connection.execute(
        "SELECT m.prospect_id,a.private_context->'marketing' AS marketing,"
        "a.private_context->>'recipient' AS recipient FROM external_actions a "
        "LEFT JOIN marketing_outreach_messages m ON m.action_id=a.id "
        "WHERE a.action_type='communications.email_send' AND "
        "(m.prospect_id IS NOT NULL OR jsonb_typeof(a.private_context->'marketing')='object')",
    ).fetchall():
        marketing = row["marketing"] if isinstance(row["marketing"], dict) else {}
        keys = (_prospect_key(row["prospect_id"]) | _prospect_key(marketing.get("prospect_id"))
                | _email_key(row["recipient"]))
        keys.update(identity_keys(marketing.get("contact_snapshot") or {}))
        keys.update(identity_keys(marketing.get("ai_research_snapshot") or {}))
        groups.append((keys, True))

    for row in connection.execute(
        "SELECT prospect_id,NULL::text AS sender,NULL::text AS creator_key FROM marketing_outcomes "
        "UNION ALL SELECT prospect_id,sender,NULL::text FROM creator_reply_messages "
        "UNION ALL SELECT prospect_id,recipient,creator_key FROM creator_automation_actions",
    ).fetchall():
        keys = _prospect_key(row["prospect_id"]) | _email_key(row["sender"])
        if isinstance(row["creator_key"], str):
            platform, separator, external_id = row["creator_key"].partition(":")
            if separator:
                keys.update(identity_keys({"platform": platform, "external_id": external_id}))
        groups.append((keys, True))

    for row in connection.execute("SELECT email FROM creator_contact_suppressions").fetchall():
        groups.append((_email_key(row["email"]), True))

    for row in connection.execute(
        "SELECT t.kind,t.payload,a.input_metadata->>'payload_hash' AS payload_hash "
        "FROM agent_tasks t JOIN audit_events a ON a.task_id=t.id WHERE "
        "(t.kind='marketing.creator_draft_batch' AND a.action='creator.draft_batch.created') "
        "OR (t.kind='marketing.creator_pilot' AND a.action='creator.pilot.created')",
    ).fetchall():
        groups.extend(_reservation_groups(row))

    for row in connection.execute(
        "SELECT prospect_ids,source_identity FROM creator_reply_deferrals",
    ).fetchall():
        for value in row["prospect_ids"]:
            groups.append((_prospect_key(value), True))
        source = row["source_identity"]
        if isinstance(source, list):
            keys = {tuple(key) for key in source if isinstance(key, list)
                    and ((len(key) == 2 and key[0] in {"email", "profile", "channel"})
                         or (len(key) == 3 and key[0] == "creator"))
                    and all(isinstance(value, str) for value in key)}
            groups.append((keys, True))
    return HistoryIndex(groups)

"""Prove scheduler rollback and concurrency in an empty disposable database."""

import os
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import psycopg
from app.career_models import CareerProfileCreate
from app.marketing_models import MarketingCampaignCreate
from app.marketing_store import MarketingStore
from app.models import TaskCreate
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def exercise(dsn):
    store = MarketingStore(dsn)
    profile = store.create_profile(CareerProfileCreate(
        name="Synthetic scheduler mission", candidate_name="Synthetic Candidate",
        desired_titles=["Engineer"], active=True, requested_by="scheduler-smoke",
    ))
    campaign = store.create_campaign(MarketingCampaignCreate(
        name="Synthetic scheduler campaign", product_name="Fixture Product",
        product_url="https://example.com/product", privacy_url="https://example.com/privacy",
        product_summary="A synthetic product used for isolated scheduler verification.",
        target_audience="Minecraft creators", viewer_offer="Fixture benefit",
        creator_offer="Fixture collaboration", paid_offer_enabled=False,
        sender_name="Fixture Sender", discovery_queries=["Minecraft server"],
        active=True, requested_by="scheduler-smoke",
    ))
    passed = []

    class FailingStore(MarketingStore):
        def _create_task_record(self, connection, request):
            super()._create_task_record(connection, request)
            raise RuntimeError("Injected failure after task, audit, and outbox creation")

    for table, row, method, kind, prefix in (
        ("career_profiles", profile, "schedule_due_profiles", "career.search",
         "career-scan"),
        ("marketing_campaigns", campaign, "schedule_due_campaigns", "marketing.creator_discovery",
         "marketing-discovery"),
    ):
        # Identifiers are fixed above, never supplied by a caller or model.
        with store.connect() as connection:
            due = connection.execute(
                f"UPDATE {table} SET next_scan_at = now() - interval '1 minute' WHERE id = %s "
                "RETURNING next_scan_at", (row["id"],),
            ).fetchone()["next_scan_at"]
            before = connection.execute(
                """SELECT (SELECT count(*) FROM agent_tasks) AS tasks,
                   (SELECT count(*) FROM audit_events) AS audits,
                   (SELECT count(*) FROM task_outbox) AS outbox""",
            ).fetchone()
        try:
            getattr(FailingStore(dsn), method)()
        except RuntimeError:
            pass
        else:
            raise AssertionError("Injected scheduling failure did not propagate")
        with store.connect() as connection:
            still_due = connection.execute(
                f"SELECT next_scan_at FROM {table} WHERE id = %s", (row["id"],),
            ).fetchone()["next_scan_at"]
            after = connection.execute(
                """SELECT (SELECT count(*) FROM agent_tasks) AS tasks,
                   (SELECT count(*) FROM audit_events) AS audits,
                   (SELECT count(*) FROM task_outbox) AS outbox""",
            ).fetchone()
        check(still_due == due and before == after, "Failure lost schedule or leaked partial task state")
        passed.append(f"{kind}: injected failure rolls back schedule/task/audit/outbox")

        start = Barrier(2)

        def schedule():
            start.wait(timeout=10)
            return getattr(MarketingStore(dsn), method)()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(schedule), pool.submit(schedule)]
            results = [item for future in futures for item in future.result(timeout=20)]
        check(len(results) == 1, "Concurrent schedulers did not create exactly one occurrence")
        task = store.get_task(results[0]["task_id"])
        check(task["kind"] == kind and task["status"] == "queued" and task["risk_level"] == "low",
              "Scheduled task did not traverse allowlisted policy")
        with store.connect() as connection:
            outbox = connection.execute(
                "SELECT count(*) AS value FROM task_outbox WHERE task_id = %s AND topic = 'career.ready'",
                (task["id"],),
            ).fetchone()["value"]
            audits = connection.execute(
                "SELECT count(*) AS value FROM audit_events WHERE task_id = %s", (task["id"],),
            ).fetchone()["value"]
        check(outbox == 1 and audits >= 1, "Scheduled task missing durable delivery/audit")
        check(getattr(store, method)() == [], "Next poll repeated an already scheduled occurrence")
        passed.append(f"{kind}: concurrent schedulers emit one audited task; repeat poll is empty")

        # Even a conflicting public idempotency key must never silently consume a due scan.
        with store.connect() as connection:
            due = connection.execute(
                f"UPDATE {table} SET next_scan_at = now() - interval '2 minutes' WHERE id = %s "
                "RETURNING next_scan_at", (row["id"],),
            ).fetchone()["next_scan_at"]
        store.create_task(TaskCreate(
            title="Synthetic conflicting key", kind="foundation.echo", requested_by="probe",
            idempotency_key=f"{prefix}:{row['id']}:{due.isoformat()}",
        ))
        try:
            getattr(store, method)()
        except ValueError:
            pass
        else:
            raise AssertionError("Conflicting idempotency key consumed a due occurrence")
        with store.connect() as connection:
            unchanged = connection.execute(
                f"SELECT next_scan_at FROM {table} WHERE id = %s", (row["id"],),
            ).fetchone()["next_scan_at"]
            connection.execute(f"UPDATE {table} SET active = false WHERE id = %s", (row["id"],))
        check(unchanged == due, "Idempotency conflict advanced schedule")
        passed.append(f"{kind}: conflicting idempotency key preserves due occurrence")
    return passed


def main():
    # The launcher provides source text only. Credentials remain inside the
    # control-api container and are never included in command arguments/output.
    migrations = globals().get("MIGRATIONS")
    if migrations is None:
        migration_root = Path(__file__).resolve().parents[1] / "config" / "postgres" / "init"
        migrations = [path.read_text(encoding="utf-8") for path in sorted(migration_root.glob("*.sql"))]
    check(bool(migrations), "No migration sources were provided")
    source_dsn = os.environ["DATABASE_URL"]
    source_database = conninfo_to_dict(source_dsn).get("dbname")
    probe_database = f"scheduler_probe_{uuid4().hex}"
    check(re.fullmatch(r"scheduler_probe_[0-9a-f]{32}", probe_database) is not None
          and probe_database != source_database, "Unsafe disposable database name")
    maintenance_dsn = make_conninfo(source_dsn, dbname="postgres", connect_timeout=10)
    probe_dsn = make_conninfo(source_dsn, dbname=probe_database, connect_timeout=10)
    created = False
    try:
        with psycopg.connect(maintenance_dsn, autocommit=True) as connection:
            connection.execute(sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(
                sql.Identifier(probe_database),
            ))
            created = True
        with psycopg.connect(probe_dsn, autocommit=True) as connection:
            for migration in migrations:
                connection.execute(migration)
        results = exercise(probe_dsn)
    finally:
        if created:
            # Drop only the exact random database created by this invocation.
            with psycopg.connect(maintenance_dsn, autocommit=True) as connection:
                connection.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(probe_database)))
    print(f"Scheduler PostgreSQL smoke passed: {len(results)} scenario groups; disposable database removed")
    for result in results:
        print(f"  PASS {result}")


if __name__ == "__main__":
    main()

# ADR-0024: Dated creator contact history

- Status: Accepted
- Date: 2026-09-26

## Decision

A creator's current research samples may differ from an earlier scan. Replacing
the dossier must not imply that an earlier published contact was never found,
or that the newly sampled video reverified an older source.

Keep current `contact_candidates` separate from `contact_history`. A merge under
the existing prospect row lock retains up to 20 distinct email/source pairs
absent from current observations, only for the same canonical channel identity.
Historical entries retain the original observation date, last actual observation
date, public source and excerpt, with status `historical_unreviewed`. Reappearance
may update the current observation date while retaining the original first date.
No merge changes reviewed recipient, authorization, suppression or offers.

Historical evidence expires 30 days after its last actual observation. Read
projection immediately excludes expired entries; a bounded worker housekeeping
pass physically trims due history and audits counts, with deadlines stored in
PostgreSQL. The normal hourly pass handles 250 records, drains a full batch again
after 30 seconds and retries failure after a minute. Restarting does not extend
evidence dates. This governs the new history field, not a complete audit of every
stored provider datum or a deletion policy for user-controlled exported files.

## Consequences

The UI, loaded-view CSV and full-campaign CSV label historical evidence separately
and provide the original source for rechecking. History never becomes a reviewed
contact or an outreach action. Current-contact coverage excludes historical-only
records, which have their own count. Identity edits clear history with other
research; suppressed creators remain protected against incoming research updates.

Public business extraction also recognizes the Polish label `Biznes`, retaining
the existing negative-context exclusions. Stored evidence validation must work
with its bounded excerpt instead of reapplying raw-description positioning rules.

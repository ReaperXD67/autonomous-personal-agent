# ADR-0011 — Governed creator discovery and adaptive outreach

Status: Accepted

Date: 2026-08-28

## Context

KarixMC needs a repeatable way to find relevant Minecraft creators, propose a
small viewer/server pilot, handle questions, measure promotion results, and
improve future messages. Creator contact data and promotional email create
privacy, platform, reputation, and spam risk. A phrase such as “promote wherever
possible” cannot safely become authority for bulk mail or public posting.

The existing control plane already freezes one recipient, subject, and body into
an approval-bound email action. PostgreSQL already owns approvals, audits, and
pre-send receipts. The new workflow must extend that boundary rather than give a
model, scraper, or scheduler direct SMTP access.

## Decision

- Discover YouTube candidates only through the official YouTube Data API v3.
  Search and channel reads use a fixed Google API host, bounded queries/results,
  strict safe search, response/time limits, and a deployment secret available
  only to the existing egress-enabled research worker.
- Store public channel/video metadata and deterministic relevance evidence. The
  YouTube API does not supply business email addresses; the system does not
  scrape, guess, buy, or infer them.
- Require an operator to add the public business address, its HTTPS source, a
  written contact-basis note, and an explicit authorization timestamp before an
  outreach plan can exist.
- Treat every email as a high-risk exact action. The existing action worker and
  SMTP transport execute one approved recipient/subject/body, create a durable
  receipt before SMTP, and never retry a consequential send automatically.
- Revalidate contact authorization, address, suppression, and reply state in the
  same PostgreSQL transaction immediately before the side-effect receipt. A
  later opt-out or state change invalidates an earlier approval.
- Use three bounded stages: one introduction, manual question answers, and at
  most one paid-option email after the operator specifically records an
  unpaid-only decline. “Do not contact,” an undifferentiated rejection, or a
  bounce suppresses the contact; it never unlocks a paid follow-up.
- Keep inbound reply reading manual until a scoped OAuth reader is designed.
  The operator classifies replies and records attributable views, clicks,
  signups, server owners, published placements, and viewer points.
- Adapt only draft selection. Two truthful introduction variants remain evenly
  assigned until both have at least ten delivered messages. A variant must lead
  positive-reply rate by at least five percentage points and 1.5× before it gets
  80% of future drafts; 20% remains exploration. Every send still requires
  approval.
- Recommendations are evidence summaries, not autonomous policy or code edits.
  The agent cannot change SMTP configuration, contact authorization, suppression,
  budget, offer terms, capability risk, approval policy, or its own source.

## Alternatives rejected

- Scraping YouTube About pages, hidden emails, or creator databases.
- Bulk or blanket-approved outreach.
- Treating every “no” as permission to send a paid offer.
- Letting an LLM classify email and answer questions without operator review.
- Automatically posting promotions to Discord, forums, social media, or creator
  accounts.
- Calling copy optimization “self-improvement” while allowing the agent to
  modify policy, code, prompts, budgets, or approval rules.

## Consequences

The dashboard can run durable creator searches, show a campaign funnel, prepare
reviewable one-to-one emails, preserve opt-outs, and suggest measured changes.
It cannot complete real discovery without a user-owned restricted YouTube API
key, cannot deliver externally without configured SMTP, and cannot discover
business emails automatically. Legal basis, truthful offer fulfillment,
sponsorship disclosure, creator negotiation, and payment remain operator-owned.

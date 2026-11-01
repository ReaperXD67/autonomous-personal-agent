# Creator outreach systems: reuse decisions

Reviewed November 1, 2026. This is a primary-source comparison of eight relevant
systems, not an exhaustive internet survey or a creator-response benchmark.
Repository metadata, default-branch commits, license files and the linked
implementation/docs were inspected. All eight repositories were unarchived;
their inspected commits span October 13–November 1 in IST. Commit links below
are observation pins, not installed releases or verified production images.

Hermes already has PostgreSQL task/outbox/approval records, exact-message review,
recipient suppression, paced SMTP, official YouTube research, reply triage and
reviewed feedback. A replacement must improve a demonstrated gap while retaining
those boundaries. Popularity and a project's feature list do not establish better
creator interest, sender reputation or compatibility with this deployment.

## Comparison

| Inspected repository | License and operating shape | Decision for Hermes |
|---|---|---|
| [listmonk](https://github.com/knadh/listmonk/tree/0c155bd2663d9ec8053ac0d1ab63f021fbb5a0dc) | [AGPL-3.0](https://github.com/knadh/listmonk/blob/0c155bd2663d9ec8053ac0d1ab63f021fbb5a0dc/LICENSE). Go/Vue, PostgreSQL; a one-way newsletter/campaign system, with batch progress and separate bounce processing. | Adapt durable batch-progress ideas in the existing research selector. Do not replace the reviewed creator conversation with a newsletter sender or copy its code into Hermes. |
| [Mautic](https://github.com/mautic/mautic/tree/ee2b5b60dd2490ecc5a1631d726cb904a5ffd06a) | [GPL-3.0-or-later](https://github.com/mautic/mautic/blob/ee2b5b60dd2490ecc5a1631d726cb904a5ffd06a/LICENSE.txt). PHP/Composer marketing platform; segmented campaigns, message translations and configurable monitored mailboxes. | Adapt explicit message-language selection and preview. Adding another marketing application/database would duplicate existing campaign, approval and delivery ownership. |
| [Dittofeed](https://github.com/dittofeed/dittofeed/tree/91277939a9afcee797ab2562025f6b02d823b00c) | [MIT community code](https://github.com/dittofeed/dittofeed/blob/91277939a9afcee797ab2562025f6b02d823b00c/LICENSE); README distinguishes separate licensed closed-source features. Its full development Compose includes PostgreSQL, Temporal, Kafka/Redpanda and ClickHouse. | Defer the platform. Event-driven customer journeys are useful, but this deployment does not justify those extra services to send a bounded creator partnership proposal. |
| [Inbox Zero](https://github.com/elie222/inbox-zero/tree/97b95cdc94cfe393d37565db5fae48ddf376c1fa) | [AGPL-based text with additional commercial/enterprise restrictions](https://github.com/elie222/inbox-zero/blob/97b95cdc94cfe393d37565db5fae48ddf376c1fa/LICENSE), rather than an unqualified permissive license. Next.js/Node, PostgreSQL, Redis and provider/model integrations; inbox rules and reply queues. | Defer installation. Its inbox workflow is relevant, but it does not establish YouTube contact provenance or authorize creator outreach; Hermes already has a narrower read-only reply queue. |
| [EmailEngine](https://github.com/postalsys/emailengine/tree/7c597f5d93b814fd772200916ccbbb07b28cd01d) | [Custom EmailEngine license agreement](https://github.com/postalsys/emailengine/blob/7c597f5d93b814fd772200916ccbbb07b28cd01d/LICENSE_EMAILENGINE.txt). Headless Node email API; its README explicitly uses Redis as the primary database. Delivery webhooks distinguish acceptance, retry failure, bounce and complaint. | Defer runtime installation: licensing and primary Redis ownership require a separate integration decision. Retain its explicit delivery-state distinction as a design reference. |
| [Twenty](https://github.com/twentyhq/twenty/tree/122818135917514ebd09c580a9c397ad57eab351) | [Mixed AGPL, commercially marked files and selected MIT packages](https://github.com/twentyhq/twenty/blob/122818135917514ebd09c580a9c397ad57eab351/LICENSE). NestJS/BullMQ/PostgreSQL/Redis CRM with extensible objects, views and workflows. | Defer a second CRM. Contact/evidence timelines are useful, but Hermes already owns prospects, outcomes and owner handoffs. Revisit only if an external CRM becomes a real operator requirement. |
| [CrewAI](https://github.com/crewAIInc/crewAI/tree/b2762ddae6edd7dae1637f81b68924db6b3ece62) | [MIT](https://github.com/crewAIInc/crewAI/blob/b2762ddae6edd7dae1637f81b68924db6b3ece62/LICENSE). Python multi-agent orchestration and event-driven Flows; its official skills teach that framework. | Defer the framework and its framework-specific skills. Extra agents do not repair stale contact evidence, language mismatch or repeated research selection; Hermes's control plane remains the execution authority. |
| [LangGraph](https://github.com/langchain-ai/langgraph/tree/e5c961d7fbe7ca6fdd4c94c84d90511372514d55) | [MIT](https://github.com/langchain-ai/langgraph/blob/e5c961d7fbe7ca6fdd4c94c84d90511372514d55/LICENSE). Stateful agent graphs with checkpoint persistence and human-review interrupts. | Defer another graph runtime. Durable progress and review are useful patterns, already implemented through Hermes's PostgreSQL policy/task boundaries. |

License descriptions report the inspected files; they do not grant permission to
reuse arbitrary files or dependencies. No upstream code, framework, remote skill
pack or executable extension was installed or executed for this comparison.

## Selected small adaptations

### Advance research instead of repeatedly selecting the same prefix

listmonk's pinned [manager store](https://github.com/knadh/listmonk/blob/0c155bd2663d9ec8053ac0d1ab63f021fbb5a0dc/cmd/manager_store.go)
retrieves each subscriber batch above the preceding batch's last ID and persists
resume checkpoints. Its [campaign queries](https://github.com/knadh/listmonk/blob/0c155bd2663d9ec8053ac0d1ab63f021fbb5a0dc/queries/campaigns.sql)
retain that progress in PostgreSQL. Mautic's [background imports](https://docs.mautic.org/en/7.1/contacts/import_contacts.html)
likewise continue from the saved row rather than restarting each batch.

Hermes now independently uses genuine server-issued reservation audits from
the preceding 24 hours, matched to canonical payload hash, current targeting
snapshot and exact profile URL. Eligible creators without a matching attempt
precede the oldest attempts, before contact/relevance tie-breakers and the
500-candidate cap. This is rolling progress rather than a lifetime cursor.
Failed/cancelled work still consumes its existing budget; idempotency, campaign
locking, contact review and sending authority remain separate. Eleven
PostgreSQL shortlist proof groups passed, including selection from a
501-candidate fixture. No listmonk code or sending semantics
were imported.

### Bind drafting language to the reviewed snapshot

Mautic's [email translations](https://docs.mautic.org/en/7.2/channels/emails.html)
associate message variants with a language and let operators preview that
variant. The useful adaptation is explicit language in a frozen draft context:
generated hooks/optional ideas and deterministic greetings/proposals support
English or Polish. Source titles and campaign-supplied free text remain as
supplied, and the mandatory English source/privacy/opt-out footer is unchanged.
The marker records a generation contract, not certification that every line has
been translated. Unsupported languages remain explicit rather than silently
being described as translated.

This is implemented in Hermes's existing constrained drafting path without a
Mautic dependency or copied translation library. The selected language is frozen
with the evidence; legacy contexts remain English. Ten PostgreSQL draft proof
groups passed, including Polish rendering. A real local Polish response also
completed, but operator review rejected its unsupported product-security claim
before preparation or sending. Immutable evidence/digests, individual approval
and final send guards remain necessary; passing schema/language checks do not
prove fluent, truthful copy or creator interest. The journal and experiment log
record the subsequent reviewed launch separately.

## Useful future work, with explicit prerequisites

[EmailEngine's delivery reference](https://learn.emailengine.app/docs/reference/webhook-events)
distinguishes an accepted outgoing message from a later bounce and identifies
auto-reply/bounce metadata. Its [bounce workflow](https://learn.emailengine.app/docs/sending/transactional-service)
correlates recipient and original Message-ID before emitting a bounce event.
Hermes currently fetches only `From` and `Subject` metadata for labeled Gmail
messages. Metadata-aware auto-responder/DSN triage would therefore need an
explicit adapter change and replay/correlation tests, not a new regex pretending
to verify deliverability from a snippet.

listmonk's [POP3 bounce collector](https://listmonk.app/docs/bounces/) deletes
processed mailbox messages. That behavior is incompatible with Hermes's
read-only Gmail contract and is not adopted. Provider webhook bounce handling
would need independently scoped credentials and authenticated, idempotent
events. No mailbox scopes, billing account, tracking pixels or public webhook
ingress were enabled by this research.

Hermes already exposes campaign result rates, contact coverage and an automation
overview. A future health projection should explain actionable gaps across those
existing facts, not duplicate counters or label SMTP acceptance as a reply rate.
[LangGraph's persistence model](https://docs.langchain.com/oss/python/langgraph/persistence)
also supports durable checkpoints and human review; adopting that principle does
not require a second state store.

## Validation boundary

This note records inspected provenance and implementation choices. It contains
no measured comparison of response rates, no universal best-repository ranking,
and no promise of replies, collaborations or revenue. The engineering journal,
experiment log and operating guide record any implementation and live-mail
proof actually completed after this research.

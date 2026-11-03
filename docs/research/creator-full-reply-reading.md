# Creator full-reply reading: source and reuse decisions

Observed November 3, 2026. The gap is access to complete reply evidence for
private review, not another classifier or sending system. This note records the
selected design; implementation, tests and live retrieval remain separate proof.
No upstream code, package or service was installed or copied for this research.

## Primary-source facts

Google's [message format reference](https://developers.google.com/workspace/gmail/api/reference/rest/v1/Format)
distinguishes metadata from `full`, which returns the parsed MIME structure and
body content in `payload`. The existing exact `gmail.readonly` grant permits
message reads; `gmail.metadata` does not permit body access. No broader OAuth
scope is needed for this extension. Label restrictions remain application checks,
not a label-limited OAuth permission. [Scopes](https://developers.google.com/workspace/gmail/api/auth/scopes),
[message GET](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/get).

The [message resource](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages)
contains nested MIME parts. A [part body](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages.attachments)
can contain base64url data or an `attachmentId` requiring a separate request.
Empty container bodies are normal. A missing required text body is not evidence
that the provider snippet is complete. `full` can include attachment metadata
or inline encoded data; the selected boundary excludes attachment endpoint calls,
decoding and persistence, rather than promising no such bytes reach the bounded
JSON response.

## Comparison

| Option and inspected provenance | Cost and fit | Decision |
|---|---|---|
| Existing allowlisted Gmail REST client plus Python standard library. The runtime already pins [CPython 3.13.14](https://github.com/python/cpython/releases/tag/v3.13.14), with [PSF License Version 2 and retained component notices](https://github.com/python/cpython/blob/v3.13.14/LICENSE). Versioned [email](https://github.com/python/cpython/blob/v3.13.14/Lib/email/message.py) and [HTML parser](https://github.com/python/cpython/blob/v3.13.14/Lib/html/parser.py) source was inspected. | No new dependency or credential owner. Reuses fixed hosts, no redirects, bounded HTTP and exact mailbox/scope checks. | **Adopt** standard-library primitives and **adapt** a small bounded walker over Gmail's already-parsed MIME JSON. |
| [google-api-python-client 2.201.0](https://github.com/googleapis/google-api-python-client/releases/tag/v2.201.0), release published September 30, 2026; commit `3974f97bbdfe42c27f0f3f246be2184e41e64291`; [Apache-2.0](https://github.com/googleapis/google-api-python-client/blob/3974f97bbdfe42c27f0f3f246be2184e41e64291/LICENSE). Release history shows continuing maintenance. | Its [dependency list](https://github.com/googleapis/google-api-python-client/blob/3974f97bbdfe42c27f0f3f246be2184e41e64291/setup.py) adds httplib2, google-auth, google-auth-httplib2, google-api-core and uritemplate. It does not decide which MIME text is complete or safe to review. | **Defer** the SDK: the existing client already supports the necessary fixed endpoint. |
| Gmail `raw` plus standard-library `BytesParser`. | No extra package, but adds full RFC-message parsing when Gmail already supplies a MIME tree. It still needs the same attachment, resource and completeness limits. | **Defer** raw-message fallback; retain one explicit JSON contract. |

Python documents [body selection versus attachment traversal](https://docs.python.org/3.13/library/email.message.html#get_body),
including traversal into `message/rfc822` submessages. Its
[base64 decoder](https://docs.python.org/3.13/library/base64.html) can validate the
alphabet strictly. [HTMLParser](https://docs.python.org/3.13/library/html.parser.html)
provides callbacks, not a browser renderer or proof that malformed markup is
complete. These are references for original code, not permission to treat mail
contents as instructions.

## Selected bounded adaptation

Keep metadata discovery/matching first. Hydrate only pending, uniquely matched
replies within the configured label, including existing metadata-only records.
The implementation further requires explicit campaign opt-in through
`CREATOR_GMAIL_FULL_REPLY_CAMPAIGN_IDS`, a JSON array of at most ten distinct
campaign UUIDs, default `[]`. Both scheduled hydration and explicit read requests
enforce it; unrelated campaigns remain metadata-only. The configuration flag is
not evidence of working credentials or successful retrieval. Existing captured
history remains privately readable when future capture is disabled.

Permit at most three full-message reads within the combined twenty-message GET
budget. Recheck mailbox, label, message/thread identity, sender, subject and
received time before persistence. Preserve the original record and review state.

Bound parsing to depth eight, sixty-four nodes, 128 KiB decoded content and
24,000 text characters, with fixed supported charsets. Prefer inline plain text;
handle supported MIME alternatives without duplicating their representations.
Skip attachments and embedded messages. Unsupported, missing, malformed or
over-limit text must remain incomplete/unavailable, never silently truncated
and called complete. Do not request attachments or follow message URLs.

Store selected plaintext, digest, completeness status and bounded attempt state
separately from snippets. Full text is private campaign/reply detail, not overview
or audit output. Permit at most three hydration attempts with a five-minute
cooldown for incomplete records. Semantic review must bind the exact stored body
digest; automatic positive decisions and sending authority are not added.
Complete MIME extraction is distinct from perfectly separating authored text,
quoted history and signatures. Preserve source evidence and keep derived hints
conservative. See [ADR-0037](../decisions/ADR-0037-bounded-creator-full-reply-evidence.md).

Verification must cover nested alternatives, attachments, malformed encoding,
unsupported charsets, every resource bound, identity/label drift, existing-row
hydration, repeat stability, cooldown/budget limits and stale/missing review
digests. Research itself establishes no live retrieval, classification accuracy,
creator interest or handoff result.

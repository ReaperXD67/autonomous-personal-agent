# Reviewed career contact outreach

Use this when an employer publishes a hiring, HR or founder email relevant to a
fresh matched job outside the posting text. Do not infer email addresses or use
support/privacy mailboxes. The API records an operator's primary-source review;
it does not search for or authenticate contacts automatically.

1. Verify the primary employer page and quote the exact published address.
   Check applicant requirements against the résumé. The current job must pass
   fit, location, job-risk and proven publication checks within 72 hours.
2. Generate a current application draft and review its cover letter, evidence
   and honest gaps. Correctable generation failures get one separately counted
   model correction; unresolved findings remain blocked.
3. Configure an SMTP sender matching the profile's application email. Gmail
   read-only OAuth cannot send mail and does not configure SMTP. Never replace
   a working creator sender merely to satisfy this check.
4. Using the authenticated API, create the reviewed contact:

   ```text
   POST /v1/career/opportunities/{opportunity_id}/contacts
   {
     "email": "hiring@example.org",
     "kind": "hiring",
     "source_url": "https://example.org/careers",
     "evidence_quote": "For this role, email hiring@example.org with your application.",
     "basis_note": "Employer careers page explicitly invites applications for this role.",
     "reviewed_by": "operator:owner",
     "attested_primary_source": true,
     "validity_hours": 24
   }
   ```

5. `POST /v1/career/contacts/{contact_id}/email-plan` with `actor` and an optional
   `approval_window_minutes` creates a pending exact-message action. Review its
   recipient, source, subject and complete body through the normal action
   approval flow. Existing Apply grants cannot approve this contact email.
6. `POST /v1/career/contacts/{contact_id}/revoke` with `actor` invalidates pending
   delivery. List source records with
   `GET /v1/career/opportunities/{opportunity_id}/contacts`.

The message uses the verified cover letter, optional portfolio and application
reference. It has no résumé attachment; it must not claim one is attached.
Acceptance means SMTP accepted the message, not that the recipient received or
read it. An uncertain delivery must not be retried as a fresh contact.

Every final send rechecks current job/profile/draft bindings, expiry/revocation,
sender identity, exact approval, shared pacing, address suppression and canonical
job/address duplicates. Accepted contact emails mark the job applied so the
normal labeled [Gmail tracking](gmail-setup.md) can match replies. Unmatched or
uncertain messages need review; inferred interviews are not calendar bookings.

For a local database proof, run `./scripts/career-contact-smoke.ps1` after starting
the stack. It applies all migrations to a disposable database and checks exact
approval/ledger bindings, concurrent and canonical duplicates, revocation, and a
Gmail opt-out racing a send. It sends no mail or external requests and removes
only its generated test database. The full `./scripts/verify.ps1` includes it.

# Free promotion activation research — 2026-08-31

## Question

What can Hermes add for KarixMC promotion without paid software, unsafe browser
profiles, hidden bulk outreach, or unsupported claims?

## Current official evidence

- The [YouTube Data API getting-started guide](https://developers.google.com/youtube/v3/getting-started)
  requires a Google account/project and API enablement. Google currently lists
  a default daily bucket of 100 `search.list` calls and 10,000 units for other
  API methods. The [search endpoint](https://developers.google.com/youtube/v3/docs/search/list)
  allows up to 50 results per request and costs one call in that search bucket.
  Hermes remains below this by allowing three queries, 25 results per query,
  daily-or-slower campaigns, and a global discovery-task cap.
- [Google Analytics campaign URL guidance](https://support.google.com/analytics/answer/10917952?hl=en)
  documents source, medium, campaign, ID, source-platform, and content parameters.
  Hermes now generates all six per promotion asset and preserves any existing
  product query parameters.
- [Google Account help](https://support.google.com/accounts/answer/185833?hl=en)
  says app passwords require two-step verification and recommends more secure
  sign-in approaches when available. [Google Workspace SMTP guidance](https://support.google.com/a/answer/176600?authuser=2&hl=en)
  documents `smtp.gmail.com`, STARTTLS port 587 or SSL port 465, full account
  address, and an app password. Hermes configures STARTTLS but cannot create the
  account credential or prove delivery without an approved test message.

Provider quotas and account options can change; recheck these primary sources
before production rollout.

## Decision

Use official YouTube metadata only for discovery, fixed TLS SMTP for individual
approved mail, and first-party UTM URLs for measurement. Add deterministic
copy-and-paste promotion assets instead of public-posting credentials. This is
zero-software-cost and keeps destination rules, disclosure, and final publication
visible to the operator.

## Rejected scope

- automated account creation, CAPTCHA, interactive Google login, or app-password
  extraction;
- scraped/guessed/enriched personal emails or bulk-sequence sending;
- unattended posts to YouTube, Discord, Reddit, or social accounts;
- paid outreach databases or analytics SaaS as a required dependency; and
- claims of external email/discovery readiness before a credentialed harmless
  request and inbox proof complete.

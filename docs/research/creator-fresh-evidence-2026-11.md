# Recent creator evidence

Reviewed November 6, 2026. The operating review found that relevance-ranked
searches repeatedly returned older matching videos. A separate shortlist could
observe a newer Minecraft upload while drafting still cited the older sample.
These are discovery and evidence-binding gaps. Reply rates remain an outcome
to measure with creators.

## Primary-source comparison

The official [search API](https://developers.google.com/youtube/data/reference/rest/v3/search/list)
provides `publishedAfter` and date ordering. Search is a bounded sample and can
have indexing or completeness limits. A recent lane can prioritize current
publications while a separately paginated relevance lane retains broader
coverage when the configured request allowance permits it. With one page per
query, only the recent lane fits. `regionCode` describes availability in a
region, and `relevanceLanguage` is a preference. Country and language selection
still use the existing observed declarations and strict/prefer rules.

The [channel uploads reference](https://developers.google.com/youtube/data/reference/rest/v3/channels#contentDetails.relatedPlaylists.uploads)
and [playlist items API](https://developers.google.com/youtube/data/reference/rest/v3/playlistItems/list)
support the existing three-upload shortlist. Playlist membership dates and the
playlist's owner are separate from a video's actual publication and uploader.
The [video resource](https://developers.google.com/youtube/data/reference/rest/v3/videos)
supplies the current channel identity, publication, privacy and upcoming state.
Those fields must agree before a video becomes current drafting evidence.

| Upstream observation | License and maintenance | Decision |
|---|---|---|
| [google-api-python-client v2.201.0](https://github.com/googleapis/google-api-python-client/releases/tag/v2.201.0), [commit 3974f97](https://github.com/googleapis/google-api-python-client/commit/3974f97bbdfe42c27f0f3f246be2184e41e64291) | [Apache-2.0](https://github.com/googleapis/google-api-python-client/blob/3974f97bbdfe42c27f0f3f246be2184e41e64291/LICENSE). Release published September 30, 2026, with preceding August releases. Its [setup](https://github.com/googleapis/google-api-python-client/blob/3974f97bbdfe42c27f0f3f246be2184e41e64291/setup.py) adds HTTP, authentication and URI-template dependencies. | Adopt documented field semantics and adapt the scheduling/evidence pattern in Hermes. Defer installing the client because the bounded standard-library adapter already owns these requests. |

The pinned [YouTube discovery schema](https://github.com/googleapis/google-api-python-client/blob/3974f97bbdfe42c27f0f3f246be2184e41e64291/googleapiclient/discovery_cache/documents/youtube.v3.json)
is a reproducible reference. No upstream code or additional runtime was imported.

## Verification targets

- Keep the original search request ceiling and durable per-request reservation.
  Track recent and relevance coverage without sharing page tokens between them.
- Validate returned video ownership, public/non-upcoming state and actual
  publication against the selected lane's window. Missing or contradictory
  current metadata cannot qualify a discovery sample.
- Use a qualifying recent Minecraft upload as the explicit shortlist's canonical
  title, URL, date and language input. A recent unrelated upload cannot make an
  old Minecraft title current.
- Preserve contact review, suppression, existing approved evidence protection,
  preparation budgets, exact-copy review and the owner's conversation holds.

Synthetic tests and a governed live rerun are recorded separately in the
engineering journal. Search coverage, qualified contacts, prepared copy, SMTP
acceptance and creator replies are distinct measurements.

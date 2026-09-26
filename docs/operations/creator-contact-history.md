# Creator contact observations

A campaign scan inspects bounded channel and video samples. A later scan may
select another video, so absence from its current candidates does not establish
that an earlier email was removed from its original source.

The dossier shows two separate sections:

- **Published business contacts** are candidates from the latest inspected
  samples. They remain unreviewed unless you separately record authorization.
- **Earlier contact observations** retain the original source, evidence excerpt,
  first observed date and last actual observation date. Recheck that source
  before relying on the contact. This section provides no approval shortcut.

Use **Earlier contact evidence to recheck** to find these records. Both CSV
exports have separate historical fields; full campaign coverage counts current
contacts and historical-only records separately. A newer dossier date never
changes the date on historical evidence.

At most 20 email/source pairs are retained per creator. Different channels never
share history solely because they use the same email. A profile identity change
clears the dossier. Suppression still prevents new research updates and outreach.

History expires 30 days after the last actual observation. It is excluded on
read immediately; a bounded worker maintenance pass trims stored expired history
without altering reviewed contact fields. Worker sleep or shutdown delays physical
cleanup until startup, but never refreshes observation dates. Exported files are
dated snapshots under the operator's control and should be refreshed when used.

The new history field follows the bounded design in
[ADR-0024](../decisions/ADR-0024-dated-creator-contact-history.md). It is not a
claim that every stored provider field or local export has undergone a complete
retention audit. Provider data obligations are described in the
[YouTube developer policies](https://developers.google.com/youtube/terms/developer-policies).

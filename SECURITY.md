# Security review through Phase 3

Reviewed 4 October 2026. This is a local learning prototype, not a campus production service.

## Fixed findings

| Finding | Impact | Fix |
| --- | --- | --- |
| Unbounded JSON request size | Memory and JSON-parser exhaustion before field validation | Reject bodies above 16 KiB before parsing, including chunked bodies |
| Unlimited in-memory report count | Repeated valid submissions exhaust memory | Phase 2 capped memory; Phase 3 replaces it with disk-backed SQL storage and bounded queries. Disk quotas and rate limits remain required before deployment |
| Unbounded list response | Large copies and responses consume resources | Default and maximum page size 100; validated limit and offset |
| Validation errors echo submitted values | Personal input unnecessarily appears in error responses | Return only error type, location, and message |
| Arbitrary hostnames accepted | Exposure to browser DNS-rebinding requests against the local API | Allow only localhost and 127.0.0.1 Host values |
| Cross-origin browser writes | A website could attempt to modify an accessible local API | Reject unsafe-method requests with untrusted Origin; allow local Swagger origins |

Responses processed by the request guard also receive `Cache-Control: no-store` and `X-Content-Type-Options: nosniff`.

## Remaining threats and boundaries

- **High: no authentication or ownership enforcement.** Anyone able to reach the API can read, edit, resolve, or delete reports. Origin and Host checks are not authentication: non-browser clients can forge these headers. Reporter names remain unverified. Run on loopback only with fictitious data. Phase 5 must bind ownership to authenticated users and enforce permissions on every operation.
- **Availability: flooding and slow requests.** Limits bound individual request size and active storage, but do not provide rate limiting, connection limits, or a complete slow-client defense. An attacker can fill the store, consume CPU, or repeatedly delete/recreate reports. Shared rate limits and reverse-proxy timeouts are needed before deployment.
- **Persistence and integrity:** Phase 3 adds durable SQLite transactions, shared file storage, database constraints, and rollback. Partial updates change only supplied columns. Concurrent edits to the same field remain last-write-wins; later editing workflows may need version checks. Backups are required to recover accidental or unauthorized deletion.
- **Privacy:** report lists expose reporter display names and locations to all API callers. Establish visibility, retention, and private claim-evidence rules before real campus use.
- **Future frontend:** report text is plain JSON data, not trusted HTML. Render it as text; do not insert it through raw HTML APIs. No student-facing HTML renderer exists yet.
- Local Host/Origin policy intentionally targets localhost:8000. Deployment and a future frontend require explicit policy configuration, HTTPS, and real access control. Do not widen the allowlist to `*` as a shortcut.

## Verification

14 tests cover HTTP CRUD, malformed/invalid fields, missing IDs, normal and chunked oversized requests, Host/Origin guards, pagination, error redaction, restart persistence, database failure recovery, constraints, rollback, concurrent inserts, and migration consistency/roundtrips.

All 18 pinned packages in the Phase 3 lockfile were queried against OSV on 4 October 2026; no matching advisories were returned. An audit is a database snapshot, not proof that dependencies are vulnerability-free. Repeat after dependency changes.

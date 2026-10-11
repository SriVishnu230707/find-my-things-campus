# Security review through Phase 6

Reviewed 11 October 2026. This is a local learning prototype, not a campus production service.

## Fixed findings

| Finding | Impact | Fix |
| --- | --- | --- |
| Unbounded JSON request size | Memory and JSON-parser exhaustion before field validation | Reject bodies above 16 KiB before parsing, including chunked bodies |
| Unlimited in-memory report count | Repeated valid submissions exhaust memory | Phase 2 capped memory; Phase 3 replaces it with disk-backed SQL storage and bounded queries. Disk quotas and rate limits remain required before deployment |
| Unbounded list response | Large copies and responses consume resources | Default and maximum page size 100; validated limit and offset |
| Validation errors echo submitted values | Personal input unnecessarily appears in error responses | Return only error type, location, and message |
| Arbitrary hostnames accepted | Exposure to browser DNS-rebinding requests against the local API | Allow only localhost and 127.0.0.1 Host values |
| Cross-origin browser writes | A website could attempt to modify an accessible local API | Reject unsafe-method requests with untrusted Origin; allow local Swagger origins |
| Anonymous and cross-user report modification | Unauthorized edits or deletion | JWT required for writes; owner/staff checks, with ownership also constrained in mutation queries |
| Client-controlled ownership or roles | Impersonation and privilege escalation | Ownership derived from authenticated account; registration always creates students; staff administration is local CLI only |
| Password exposure or modification | Credential disclosure or failed login | Argon2id hashes, redacted validation, no hashes in responses, exact password preservation |
| Forged, expired, or stale-authority tokens | Authentication bypass | Pinned HS256, required issuer/audience/expiry/subject; current account and role loaded from database |
| Authentication resource exhaustion | Password hashing consumes memory/CPU | Bounded process-local request limiter and two concurrent hash/verify operations |

Responses processed by the request guard also receive `Cache-Control: no-store` and `X-Content-Type-Options: nosniff`.

## Remaining threats and boundaries

- **Identity verification:** registration does not verify email ownership or campus membership. Anyone may register an unused email. Display names are unverified. Add verified campus identity before real use; no email delivery or password reset exists yet.
- **Token theft:** bearer tokens remain usable for up to 15 minutes. There is no per-token revocation or refresh flow. Keep secrets private, use HTTPS in deployment, and rotate the signing secret to invalidate all tokens when necessary. Deleted accounts fail authentication and database role changes apply immediately.
- **Availability: flooding and slow requests.** Authentication has a 60-request/minute/client process-local limiter, capped at 1,024 remembered clients, and two concurrent Argon2 operations. Client churn, multiple workers, report-write flooding, disk exhaustion, and slow connections still require shared rate limits, quotas, and proxy timeouts. Do not trust forwarded client headers from arbitrary clients; local startup disables them.
- **Administration:** anyone with trusted server/database access can create staff or reassign reports through the CLI. Protect that machine, the signing secret, database, and backups. Legacy reports have no owner and remain staff-only until explicitly assigned after verification.
- **Persistence and integrity:** Phase 3 adds durable SQLite transactions, shared file storage, database constraints, and rollback. Partial updates change only supplied columns. Concurrent edits to the same field remain last-write-wins; later editing workflows may need version checks. Backups are required to recover accidental or unauthorized deletion.
- **Privacy:** report lists expose reporter display names and locations to all API callers. Establish visibility, retention, and private claim-evidence rules before real campus use.
- **Future frontend:** report text is plain JSON data, not trusted HTML. Render it as text; do not insert it through raw HTML APIs. No student-facing HTML renderer exists yet.
- Local Host/Origin policy intentionally targets localhost:8000. Deployment and a future frontend require explicit policy configuration, HTTPS, and real access control. Do not widen the allowlist to `*` as a shortcut.

## Verification

Phase 6 keeps ownership evidence outside public report responses. Claim reads are restricted to the claimant's own list or the report owner/staff review list. Students cannot submit claims on their own reports or review their own claims. Database foreign keys preserve history, partial unique indexes prevent duplicate active claims and multiple winners, and serialized report transactions prevent claim/delete/archive races. Handover resolves the report and rejects other pending claims in one transaction. Ordinary report type/status edits cannot bypass this workflow.

Claim evidence is sensitive stored text, not encrypted application data. Trusted machine/database administrators can read it. Define retention, encryption, backups, account verification, and claim submission quotas before real campus use. Approval records a human decision rather than proving physical ownership.

42 tests cover CRUD, search, persistence, constraints, migration consistency and ID preservation, request guards, account/password validation, expired/tampered/invalid JWTs, deleted accounts, forged role claims, anonymous and cross-user access, staff moderation, immediate role changes, legacy ownership assignment, bounded authentication resources, claim privacy and transitions, simultaneous approval/submission, handover, archival, and claim persistence after restart, and rejected ownership reassignment to claimants or archived reports. Security headers also cover early guard rejections.

An Edge browser check against an isolated database verified Swagger OAuth2 login, authenticated report creation, rendered account profile, persisted owner updates, public reads, anonymous 401 responses, and cross-user 403 responses.

Phase 6 browser verification additionally covered Swagger claim submission and evidence rendering, private review denial, approval, persisted handover/resolution, deletion conflicts, and successful archival.

All 26 pinned packages were queried against OSV on 11 October 2026; no matching advisories were returned. An audit is a database snapshot, not proof that dependencies are vulnerability-free. Repeat after dependency changes.

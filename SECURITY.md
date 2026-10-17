# Security review through Phase 9

Updated 17 October 2026. This is a local learning prototype, not a campus production service.

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

- **Identity verification:** students must verify their email before report/claim writes by default. Campus membership is claimed only when the verified address exactly matches a configured college domain. Without the real domain allowlist, verification proves inbox access only. Display names remain unverified. Local email mode writes private development messages rather than delivering mail; configure and test TLS SMTP before real use. Development compatibility mode must not be used to bypass verification in a campus pilot.
- **Token theft:** bearer tokens remain usable for up to 15 minutes. Password resets and account status changes revoke all account sessions through a database version check. There is no individual-token revocation or refresh flow. Keep secrets private, use HTTPS in deployment, and rotate the signing secret to invalidate all tokens when necessary. Deleted/disabled accounts fail authentication and database role changes apply immediately. Already-authorized in-flight requests are not guaranteed to be cancelled.
- **Availability: flooding and slow requests.** Authentication has a 60-request/minute/client process-local limiter, capped at 1,024 remembered clients, and two concurrent Argon2 operations. Client churn, multiple workers, report-write flooding, disk exhaustion, and slow connections still require shared rate limits, quotas, and proxy timeouts. Do not trust forwarded client headers from arbitrary clients; local startup disables them.
- **Administration:** anyone with trusted server/database access can create staff or reassign reports through the CLI. Protect that machine, the signing secret, database, and backups. Legacy reports have no owner and remain staff-only until explicitly assigned after verification.
- **Persistence and integrity:** Phase 3 adds durable SQLite transactions, shared file storage, database constraints, and rollback. Partial updates change only supplied columns. Concurrent edits to the same field remain last-write-wins; later editing workflows may need version checks. Backups are required to recover accidental or unauthorized deletion.
- **Privacy:** report lists expose reporter display names and locations to all API callers. Establish visibility, retention, and private claim-evidence rules before real campus use.
- **Frontend:** report text and claim evidence are inserted with DOM text APIs, never raw HTML. Tokens are kept in memory, with no local/session storage persistence. Refreshing signs out; logout clears personal results. This reduces persistence of credentials but cannot defend a live page against compromised same-origin scripts. The website is served on the API origin, retaining Host/Origin guards.
- Local Host/Origin policy intentionally targets localhost:8000. Deployment and a future frontend require explicit policy configuration, HTTPS, and real access control. Do not widen the allowlist to `*` as a shortcut.

## Verification

Phase 9 stores only SHA-256 digests of cryptographically random, purpose-bound verification/reset tokens. Links expire, are consumed once under an account lock, and are replaced on later requests. Persistent per-account cooldowns supplement the local authentication limiter. Password resets revoke old JWTs, preserve password spaces, and roll back token use if the transaction fails. Email requests return generic responses for missing/ineligible accounts and delivery failure; this is not a constant-time or distributed anti-enumeration guarantee.

Staff routes check the current account's active role, and web account status changes recheck authority under a lock. Public registration cannot assign roles, verified status, or activity flags. Staff accounts cannot be disabled through the web API. Moderation events commit with their action and survive report deletion, excluding tokens/passwords/private claim evidence from automatic audit details. Staff-entered moderation reasons are trusted operational text and must not include secrets. Audit history remains editable by a trusted database administrator.

Local `.eml` messages contain live secrets: they are ignored by Git, never exposed by HTTP, and require filesystem protection and retention cleanup. Browser links use fragments rather than query strings, are scrubbed on initial/same-tab navigation, and require explicit confirmation so link scanners do not consume tokens through GET. SMTP uses certificate-verified STARTTLS or SSL; actual provider delivery requires credentials and a real integration check. Deployments still require HTTPS, configured campus domains, shared throttling, and protection for staff accounts.

Phase 8 accepts only bounded JPEG/PNG photo uploads and checks decoded content against media type. It rejects animations, invalid images and excessive dimensions, limits concurrent decodes, re-encodes onto a clean canvas without metadata, and bounds stored JPEG size. Photos are public database BLOBs rather than executable or user-named filesystem uploads. Photo writes recheck ownership and archival under the report lock. Only the exact photo PUT path receives the larger multipart body allowance; other endpoints retain 16 KiB guards.

Notifications are recipient-scoped even for staff. Private evidence is never included. Claim events and notifications commit together; unsuccessful competing approvals and retries do not emit phantom events. Inbox writes cannot mark another user's records read. Session expiry clears private UI results and closes dialogs; photo upload retries reuse an already-created report.

Photos and notifications increase disk usage. Enforce account/upload quotas, retention and operational rate limits before campus deployment. SQLite stores image data and backups retain it; logical deletion is not secure erasure. Production media delivery and external object storage require their own deployment verification. Notification read state is not proof that a physical handover happened.

Phase 6 keeps ownership evidence outside public report responses. Claim reads are restricted to the claimant's own list or the report owner/staff review list. Students cannot submit claims on their own reports or review their own claims. Database foreign keys preserve history, partial unique indexes prevent duplicate active claims and multiple winners, and serialized report transactions prevent claim/delete/archive races. Handover resolves the report and rejects other pending claims in one transaction. Ordinary report type/status edits cannot bypass this workflow.

Claim evidence is sensitive stored text, not encrypted application data. Trusted machine/database administrators can read it. Define retention, encryption, backups, account verification, and claim submission quotas before real campus use. Approval records a human decision rather than proving physical ownership.

60 tests cover CRUD, search, persistence, constraints, migration consistency and ID preservation, request guards, account/password validation, expired/tampered/invalid JWTs, deleted accounts, forged role claims, anonymous and cross-user access, staff moderation, immediate role changes, legacy ownership assignment, bounded authentication resources, claim privacy and transitions, simultaneous approval/submission, handover, archival, and claim persistence after restart, website assets/security headers, authenticated own-report filtering before pagination, and rejected ownership reassignment to claimants or archived reports. Security headers also cover early guard rejections.

An Edge browser check against an isolated database verified Swagger OAuth2 login, authenticated report creation, rendered account profile, persisted owner updates, public reads, anonymous 401 responses, and cross-user 403 responses.

Phase 6 browser verification additionally covered Swagger claim submission and evidence rendering, private review denial, approval, persisted handover/resolution, deletion conflicts, and successful archival.

All 31 pinned runtime packages were queried against OSV on 17 October 2026; no matching advisories were returned. An audit is a database snapshot, not proof that dependencies are vulnerability-free. Repeat after dependency changes.

Phase 10 adds explicit production startup requirements, private authenticated Redis throttling with fail-closed writes, PostgreSQL TLS validation for external services, configured Host/Origin policies, protected metrics, request IDs and route-based logs. The Compose template terminates HTTPS at Caddy and trusts forwarded headers only from its fixed proxy address. Internal Docker database/Redis traffic uses an explicit TLS exception; external deployments must retain verified TLS. Metrics are process-local, and application throttles do not replace host/network denial-of-service protection. Backups require private off-host storage and restore drills; the template alone does not establish those operations. See deploy/README.md for migration and recovery precautions.

Phase 7 Edge verification exercised registration, report creation, personal reports, search, private claims, review, approval, handover, archival filters, report edits/deletion confirmations, safe rendering of HTML-like titles, signout privacy, and mobile layout. Website responses include a Content Security Policy restricting scripts and styles to this origin and blocking embedding.

Phase 8 adds photo type/size/dimension and metadata checks, replacement/removal and restart persistence, staff upload permissions, notification privacy/read state/legacy routing, atomic notification failure rollback, and bounded decoder work. Edge verification covered photo preview and public rendering, removal/replacement, retry without duplicate reports, submission/approval/handover inbox events, read controls, mobile layout, and expired-session cleanup.

Post-Phase 8 regression: claim-storage integrity failures return generic 503 and roll back instead of falsely reporting a duplicate claim. Active duplicate claims are checked under the report lock and remain protected by the database unique index. Browser verification confirmed whitespace-only search/location values are omitted rather than sent as invalid empty filters.

Phase 9 tests additionally cover domain enforcement, verification gates, token expiry/replacement/purpose/single use, concurrent resets, exact password handling, session revocation, disabled accounts, generic delivery failures, rollback-safe recovery, staff permissions, persistent moderation history, and the TLS SMTP adapter. Edge checks exercised same-tab verification links and URL scrubbing, verified report/claim flows, staff overview/queues/audit/account controls, recovery with revoked prior sessions, and mobile layout.

# InternPilot-AI: engineering audit

Audit date: 2026-10-28. Scope: the source currently in `/workspace/internpilot-ai`.
Status: read-only application audit; this report is the only intended repository change. No deployment, external application, document upload to an employer, or outgoing message was performed.

## Executive assessment

The existing stack can support continued incremental development. It contains substantial working implementation: authenticated tenant-scoped APIs, encrypted candidate data, deterministic eligibility extraction, public-source connectors, a durable database queue, browser safety checkpoints, resume generation, and Gmail integration code. Preserve those controls.

Massive-scale readiness has not been established. The principal blockers are incorrect inventory-completeness handling, discovery writes without lease fencing, synchronous database work inside asynchronous workers, repeated full-catalog evaluation, and duplicated public crawling per tenant. Fix correctness and concurrency before raising worker counts. A higher configured concurrency is not evidence of higher sustainable throughput.

Severity meanings: **High** = credible data corruption, approval/reply-policy failure, or major reliability/scalability blocker; **Medium** = bounded correctness, availability, or engineering defect; **Low** = limited user-facing inconsistency. None of the inspected evidence establishes an exploitable critical vulnerability or an actual cross-tenant data leak.

Evidence labels:

- **Reproduced:** an isolated diagnostic executed during this audit, using synthetic inputs and fake transports.
- **Confirmed implementation:** the cited code establishes the behavior or missing invariant; its production frequency/latency has not been measured.
- **Risk / unresolved:** needs an experiment, runtime configuration, or provider credentials before a stronger conclusion.

Line references describe the audited snapshot. Links below are repository-relative so they remain useful outside this workspace.

## Architecture and capabilities actually found

| Area | Implementation and limits |
| --- | --- |
| Web | Next.js 15 / React 19 / TypeScript. Most authenticated screens share one client component and client state in `frontend/src/app/page.tsx`; specialized explorer, outreach, source-manager and owner-console components exist. Rounded light/dark UI, real backend metrics and paginated explorer exist. |
| API and storage | FastAPI with synchronous SQLAlchemy sessions. PostgreSQL supported; SQLite used for local operation/tests. Custom numbered migrations through version 5, PostgreSQL advisory migration lock. Candidate fields, documents and OAuth tokens use Fernet; passwords use scrypt, not reversible storage. |
| Queue | Database `Task` records, dedupe keys, atomic claims, leases, retries, expired-lease recovery and role-separated workers. Redis supports coordination/realtime; this is not a Celery queue. PostgreSQL remains the durable task source of truth. |
| Discovery | Greenhouse, Lever, Ashby, bounded SmartRecruiters and Workday, permitted RSS/Atom and JSON-LD pages; MLH calendar, InternScan public feed, SimplifyJobs link references, configured JobSpy export feeds, and authorized Brave search. A feed adapter is not an embedded JobSpy scraping runtime. |
| Unsupported/restricted sources | There is no demonstrated universal LinkedIn/Indeed/Wellfound/Internshala integration. Restricted-platform direct crawling is explicitly blocked in `discovery.py:33,66–94`. Devpost is represented in connector code, but its current live availability is not established by this audit. Do not advertise Devfolio, Unstop, HackerEarth or DoraHacks as individually verified native integrations without evidence. |
| Matching | Deterministic rules and explainable scores are authoritative. Graduation constraints, quoted evidence, unsupported mandatory conditions and geographic/work-authorization uncertainty are handled conservatively. Optional structured LLM analysis remains unverified annotation and cannot promote itself to eligibility truth. Scores are heuristics, not calibrated probabilities. |
| Documents | Resume parsing creates proposals requiring user verification. Template-based tailored PDFs use verified candidate facts; originals and versions are encrypted in the database. This is useful document automation, not evidence of a general generative resume agent. |
| Applications | Explicit upload/submit consent, content digests, daily limits, dedupe, lease checks and uncertain-outcome handling exist. The only implemented final-submit path is the isolated local test portal. External preparation disables JavaScript and blocks mutations; there is no demonstrated external ATS submission adapter. |
| Gmail | OAuth, encrypted refresh tokens, approved drafts, send spacing/quota checks, reply/bounce processing and reconciliation code exist. Provider transport is implemented; no real Gmail OAuth/send/reply test was executed in this audit. |
| Notifications | In-app notifications plus SMTP, Telegram and authorized Twilio adapters exist. External delivery is explicitly approved per delivery (`notification_delivery.py:295–357`). Quiet hours can require reapproval. Do not describe this as unattended delivery of every alert. Provider acceptance is not inbox delivery. |
| Deployment | Docker/cloud Compose separates API, crawlers, browser workers and outreach; Caddy provides an HTTPS configuration. Managed PostgreSQL, Redis and persistent volumes are configured. Files are not evidence of a deployed service, multi-host failover, or a successful backup restore. |

## Prioritized findings

Effort estimates are relative implementation sizes, not delivery promises: S = localized; M = several components; L = data-model/architectural migration. Risk means risk introduced by the correction. Interview value rewards demonstrable invariants, fault injection and measured results rather than adding integrations.

| ID | Priority / severity | Change | Impact | Effort | Change risk | SDE interview value |
| --- | --- | --- | --- | --- | --- | --- |
| F01 | P0 High | Correct source completeness and pagination | Prevent false closures and missing listings | M | Medium | High |
| F02 | P0 High | Validate connector response contracts | Prevent whole-board false closures | S–M | Low | High |
| F03 | P0 High | Fence discovery commits after lease loss | Prevent stale-worker data corruption | M | Medium | Very high |
| F04 | P0 High | Check the exact follow-up thread before sending | Preserve stop-on-reply/opt-out intent | M | Medium | High |
| F05 | P1 High | Remove blocking DB work from worker event loops | Reliable leases and bounded concurrency | L | Medium | Very high |
| F06 | P1 High | Build indexed opportunity/evaluation read models | Predictable API cost as catalogs grow | L | Medium | Very high |
| F07 | P1 High | Reduce frontend refresh fan-out | Reduce read amplification and UI work | M | Low–medium | High |
| F08 | P1 High | Share public crawling across tenants | Avoid repeated provider and LLM costs | L | High | Very high |
| F09 | P1 Medium | Batch ingestion and normalize memberships | Shorter transactions, fewer round trips | M | Medium | High |
| F10 | P1 High | Canonicalize requisition identity | Prevent cross-URL duplicate applications | M | Medium | High |
| F11 | P1 Medium | Enforce refresh cooldowns and request quotas | Bound provider/resource use | S–M | Low | High |
| F12 | P1 Medium | Shared authentication throttling | Predictable protection across replicas | M | Medium | High |
| F13 | P1 Medium | Fair, cursor-based Gmail scheduling | Prevent history/account starvation | M | Medium | High |
| F14 | P2 Medium | Database reference/tenant invariants | Prevent orphaned or mislinked records | L | Medium–high | High |
| F15 | P2 Medium | Atomic document version allocation | Reliable document histories | S–M | Low | High |
| F16 | P2 Medium | Model-call singleflight and global budgets | Avoid duplicate paid work | M | Low–medium | High |
| F17 | P2 Medium | Real role-aware worker health | Detect missing processing capacity | S–M | Low | High |
| F18 | P2 Medium | Isolate source/tenant failure backpressure | Avoid fleet-wide slowdown from one outage | M | Medium | High |
| F19 | P2 Medium | Provide an honest usable browser handoff | Make assistance useful on supported forms | M–L | Medium | Medium |
| F20 | P2 Medium | Route/split/type frontend screens | Navigation, maintainability, rendering control | M–L | Medium | High |
| F21 | P2 Medium | Make migration/backfill operations bounded | Safer upgrades on large installations | M | Medium | High |
| F22 | P3 Low | Align resume upload limit | Remove an avoidable failed upload | S | Low | Low |

### F01 — Incomplete ATS pages can become authoritative inventories

- **Evidence/status:** reproduced SmartRecruiters with 30 relevant synthetic postings: `discover()` returned 20 and `cache.truncated == False`. [`discovery.py:381`](../backend/app/discovery.py#L381) requests only offset 0; lines 465–482 stop after 20 details but only mark truncation when `totalFound > 100`. [`services.py:366–384`](../backend/app/services.py#L366) treats an untruncated result as complete and marks unseen linked opportunities inactive. The downstream closure consequence is established by source inspection, not a live employer experiment.
- **User impact:** valid internships disappear or receive false closure alerts. Opportunities after the same first 20 can remain undiscovered indefinitely.
- **Scaling impact:** fixed first-page budgets defeat broad board coverage. Workday similarly always fetches offset 0 / limit 20 (`discovery.py:403–404,483–492`); it flags partial results but never advances a durable cursor.
- **Correction:** return a typed completeness result with page/cursor provenance, separate listing IDs from fetched details, persist continuation state, and close only against a successfully completed inventory generation. Rotate bounded detail verification fairly.
- **Validation:** contract fixtures with 30 and 150 postings; unchanged and reordered pages; changed details; restart between pages. Assert all IDs eventually discovered and no unvisited listing falsely closed.

### F02 — Unexpected HTTP 200 schemas are accepted as empty complete boards

- **Evidence/status:** reproduced a Greenhouse HTTP 200 JSON `{message: 'unexpected schema'}`: zero jobs, no error, no partial flag. [`discovery.py:437–438`](../backend/app/discovery.py#L437) uses `data.get('jobs', [])`; Ashby, SmartRecruiters and Workday have analogous defaults at 455,463,487. Lever checks the top-level list type at 445. Closure logic is the F01 path.
- **User impact:** an upstream schema change or error-shaped success response can close existing listings and claim a healthy zero-result scan.
- **Scaling impact:** one provider change affects every subscribed board; repeated scans propagate bad state.
- **Correction:** strict provider-specific response contracts, explicit empty-inventory evidence, and failed/partial scan states that preserve prior inventory. Distinguish schema errors from genuinely empty boards.
- **Validation:** malformed type, missing required collection, error object, partial body and legitimate empty fixtures for each connector. Assert schema errors cannot trigger closure or advance the last-complete inventory.

### F03 — Discovery side effects are not fenced by the task lease

- **Evidence/status:** confirmed implementation. [`worker.py:184–191`](../backend/app/worker.py#L184) passes task/lease identity to application work, but calls `process_discovery(owner, source)` without it. [`services.py:273,315–404`](../backend/app/services.py#L273) commits opportunity, membership, closure and source-cache changes without proving the worker still owns a live lease. `worker.py:65` recovers expired tasks. Locking the source row at commit serializes writes but does not establish which scan is newest.
- **User impact:** after lease expiry/reassignment, a delayed older scan can overwrite a newer scan or close newly discovered listings.
- **Scaling impact:** more replicas, network delays and restarts increase overlapping execution. A lease-aware task acknowledgment cannot undo previously committed side effects.
- **Correction:** assign a monotonically increasing source generation/fencing token at claim; condition every inventory commit on the current generation and live task lease. Discard stale results. Recheck disable/permission/emergency-stop state at the write boundary too.
- **Validation:** barrier-controlled two-worker test: expire A, let B commit newer results, then release A. Assert A changes neither opportunities nor source cache/status. Repeat with deletion and permission revocation during fetch.

### F04 — Follow-up safety refresh may not inspect the recipient's thread

- **Evidence/status:** confirmed implementation. [`outreach.py:123–129`](../backend/app/outreach.py#L123) calls generic `sync_replies(owner)` before follow-up. That function loads all sent messages, rotates only 25 (`234–241`), and inspects only the first 100 returned messages per thread (`247`). The send gate at `155` only knows replies already persisted. The target thread need not be in that batch.
- **User impact:** an approved follow-up can be sent despite an already-existing reply/opt-out that this batch did not inspect. No real message was sent to reproduce this condition.
- **Scaling impact:** growing sent history lengthens reply detection; duplicate message rows from one thread waste the bounded batch.
- **Correction:** synchronize the exact recipient/thread before a follow-up; fail closed on verification failure, then check suppression immediately before reservation/send. Use Gmail history cursors or verified watch/delta processing plus distinct thread identities and durable suppression.
- **Validation:** 26+ threads with the selected recipient outside the rotating batch and a preexisting reply; assert zero provider sends. Add a thread exceeding 100 messages with the latest reply/opt-out beyond the current slice and concurrent sync/send tests.

### F05 — Synchronous database work runs inside asynchronous workers

- **Evidence/status:** confirmed implementation, no throughput or deadlock benchmark. [`worker.py:171–179`](../backend/app/worker.py#L171) performs synchronous lease updates in an async heartbeat. `run_worker():280–300` invokes synchronous maintenance directly. `process_discovery():315–404` performs ORM reads/writes and per-job work on the loop. [`gmail.py:115–138`](../backend/app/gmail.py#L115) takes a synchronous user row lock and holds it while awaiting a token refresh at 127.
- **User impact:** slow DB/CPU work can stall unrelated tasks and lease renewal. Two same-user Gmail operations with an expired token can cause an event-loop/row-lock interlock: one awaits the provider while the other synchronously waits for its lock. Actual occurrence is unmeasured.
- **Scaling impact:** configured async task slots do not isolate blocking database waits; adding concurrency can increase lock/pool contention and expired leases.
- **Correction:** choose consistent async SQLAlchemy/driver boundaries or bounded thread execution for complete synchronous units of work. Keep transactions short; never await provider I/O while holding a synchronous row lock. Serialize token refresh with a short-lived distributed reservation, then compare-and-swap the result. Move CPU-heavy document work into bounded workers.
- **Validation:** event-loop lag and heartbeat-delay instrumentation; delayed DB/provider fault injection; concurrent expired-token Gmail requests; kill/restart under load. Verify no task side effects after lease loss.

### F06 — Hot read paths still scan and repeatedly evaluate the full catalog

- **Evidence/status:** confirmed implementation. [`services.py:48–56`](../backend/app/services.py#L48) loads every visible ORM opportunity even to locate one ID. [`main.py:779–794`](../backend/app/main.py#L779) evaluates every real opportunity and loads all applications for dashboard metrics. [`opportunity_query.py:135–179`](../backend/app/opportunity_query.py#L135) scans all candidates even in chronological mode to calculate totals/top-K; score/filter mode also evaluates each candidate. Deep pages retain `offset + page_size` entries. SQL prefilters and batch hydration exist and should be preserved; chronological pages only evaluate selected rows, but still examine the candidate catalog.
- **User impact:** slower dashboard, searches and single-opportunity actions as history grows.
- **Scaling impact:** repeated O(N) Python/JSON work per client; large aggregate histories compete with crawling. [`models.py:155–162`](../backend/app/models.py#L155) stores most searchable/sortable facts in JSON without corresponding typed indexes.
- **Correction:** indexed typed opportunity read model, keyset pagination, compact list projection and cached aggregate counters. Persist evaluations by `(profile_version, opportunity_version, rules_version)`; invalidate on relevant changes. Fetch a single authorized ID with SQL. Preserve timezone/unknown-status semantics during migration.
- **Validation:** PostgreSQL EXPLAIN ANALYZE and statement/evaluation counts at representative 10k/100k/1m histories, skewed tenants and concurrent crawler traffic. Establish measured p95 latency/memory targets; do not extrapolate SQLite synthetic timings into production throughput.

### F07 — One frontend refresh fans out to nine endpoints regardless of screen

- **Evidence/status:** confirmed implementation. [`page.tsx:91–135`](../frontend/src/app/page.tsx#L91) refreshes dashboard, scored opportunities page, applications, documents, sources, events, tasks, notifications and health together. Visible-page polling runs every 15 seconds; SSE events can schedule refreshes with a two-second coalescing window. The root opportunity request defaults to score sorting even when the visible explorer is chronological. Singleflight, hidden-tab suppression and account epoch guards already reduce redundant/racy work.
- **User impact:** unnecessary requests and state updates while using a single screen; one endpoint failure can show a global load error despite other views being usable.
- **Scaling impact:** the timer alone implies nine requests per 15-second cycle per active client, excluding SSE-triggered refresh and screen-specific requests. This is code-derived request arithmetic, not a measured QPS result. It repeatedly invokes F06.
- **Correction:** per-resource private caches, view-driven loading, targeted SSE invalidation, conditional requests/version tags and a cheap overview summary. Keep post-mutation consistency and account-bound cache clearing. Do not publicly cache PII.
- **Validation:** browser network assertions for each idle/open view, worker bursts and hidden tabs; compare backend query/evaluation counts before/after; two-account sign-out/sign-in race tests.

### F08 — Public crawling and opportunity storage are duplicated per account

- **Evidence/status:** confirmed architecture. Sources are owner-specific (`models.py:134–151`); registration creates default sources (`main.py:151–153`). [`services.py:339`](../backend/app/services.py#L339) incorporates owner ID into opportunity fingerprints. Source caches and crawl work are therefore repeated for accounts following the same public board.
- **User impact:** shared rate budgets get consumed by repeated fetching of identical public material; discoveries can arrive at different times across accounts.
- **Scaling impact:** source fetches, parsing, public listing storage and optional LLM analysis grow with tenants × subscribed sources instead of unique permitted sources. Tenant isolation here is intentional; removing it carelessly would be a privacy regression.
- **Correction:** separate a global public source/requisition inventory from private subscriptions, saved records, profiles, matches and applications. Include access-policy/credential scope in source identity; never globally share authenticated or private feeds. Stage the migration with tenant-safe dual reads and explicit authorization tests.
- **Validation:** 100 synthetic tenants subscribing to one public source should cause one scheduled provider fetch per refresh window; private source results remain isolated and unsubscribe/deletion behavior is preserved.

### F09 — Ingestion makes per-record queries and stores growing memberships in JSON

- **Evidence/status:** confirmed implementation. `process_discovery():322–392` hydrates all source-linked jobs, selects by fingerprint for each listing (`340`), checks saved state/membership individually (`354,360`), and uses per-record savepoints on creation (`346–348`). Complete closure loads all other tenant sources and searches cached active-ID lists (`371–379`). Source cache stores active/verified ID arrays (`392`) alongside normalized `SourceOpportunity` records.
- **User impact:** larger boards take longer to reconcile; scans hold the source row lock while doing many reads/writes.
- **Scaling impact:** O(listings) round trips plus growing JSON serialization and cross-source membership scans; memory is proportional to linked history.
- **Correction:** batch key reads/upserts, set-based membership updates and versioned `source_opportunity` presence/last-seen/completeness columns. Remove duplicated membership arrays after compatibility migration. Retain unique fingerprints and safe upsert conflict handling.
- **Validation:** statement-count assertions for 1/100/1000 listings, large overlap across sources, unchanged scans and concurrent arrivals. Verify closure and saved-change notifications remain identical.

### F10 — URL identity does not prevent duplicate applications to one requisition

- **Evidence/status:** confirmed identity limitation. [`services.py:240`](../backend/app/services.py#L240) bases canonical fingerprints on canonical URL. `discovery.py:59–63` removes tracking parameters but cannot unify a company landing URL, ATS URL and alternate board URL for the same requisition. Application uniqueness is `(owner_id, opportunity_id)` (`models.py:184–186`).
- **User impact:** one actual role represented by different opportunity IDs can appear twice and acquire separate application records.
- **Scaling impact:** aggregation and additional sources amplify alias duplicates and distort metrics/ranking.
- **Correction:** provider + employer + stable external requisition ID, explicit URL aliases and evidence-backed identity merges. Keep ambiguous matches separate for review; do not fuzzy-merge unrelated same-title roles. Point application idempotency at a stable canonical requisition.
- **Validation:** same requisition via two official URLs/one reference feed yields one application identity; distinct requisitions with identical company/title remain separate; preserve existing application history through alias migration.

### F11 — Manual discovery can bypass the successful-source refresh interval

- **Evidence/status:** confirmed implementation. [`main.py:473–483`](../backend/app/main.py#L473) queues requested discovery; `services.py:296` checks a future `next_run` only when `source.failures` is nonzero. Successful sources therefore remain immediately rerunnable after task completion. Shared host throttling exists, but it is not the configured per-source refresh interval.
- **User impact:** repeated clicks or API calls waste scan work/provider quota; other useful checks wait behind them.
- **Scaling impact:** authenticated users can generate repeated discovery/optional LLM work. Several expensive mutation endpoints also lack a coherent per-account resource budget; no unlimited external send capability was established.
- **Correction:** enforce next-allowed-at for both manual and scheduled requests; coalesce refresh intent, return the existing task/next refresh time, and introduce per-tenant discovery/document/import budgets. Reserve force-refresh for audited operations subject to provider limits.
- **Validation:** repeated requests before and after completion must not fetch before cooldown; failed-source Retry-After remains authoritative; unrelated tenants remain fairly scheduled.

### F12 — Authentication throttling is process-local

- **Evidence/status:** confirmed implementation. [`main.py:100–110`](../backend/app/main.py#L100) uses an in-memory dictionary keyed by `request.client.host`, with 20 attempts/300 seconds. Keys for old addresses are never evicted. Replica/restart behavior follows from local memory. The actual client IP behind the deployed proxy is unresolved, not a demonstrated configuration failure.
- **User impact:** process restarts/replica distribution weaken throttling; if proxy identity is not correctly trusted, unrelated users could share the same limit. Unbounded distinct keys retain memory.
- **Scaling impact:** behavior changes as API replica count changes; there is no shared account-based anti-password-spray budget.
- **Correction:** bounded TTL shared token buckets for IP and normalized account identity, explicit trusted-proxy configuration, and provider-independent resource quotas. Avoid logging credentials or revealing account details in throttle errors.
- **Validation:** two API instances, process restart, trusted/untrusted forwarding headers, shared proxy users and distributed attempts against one account. Verify owner/member authorization separately.

### F13 — Gmail scheduling has hard coverage caps and rescans growing history

- **Evidence/status:** confirmed implementation. [`outreach.py:117–119`](../backend/app/outreach.py#L117) selects at most 1000 connected accounts without a durable cursor/order. `sync_replies():234–242` loads all historical sent-message rows before selecting 25; `sync_bounces()` also reads sent history. Due sends are limited to 200 at 114; blocked/disabled senders can leave old approved rows eligible because `send_message():138–145` returns without deferring/changing them.
- **User impact:** accounts outside a stable first 1000 can miss automatic reply sync; blocked rows may repeatedly consume scheduling slots ahead of other work.
- **Scaling impact:** unbounded memory/history reads and unfair account coverage. The first-1000 cap is confirmed; starvation frequency with a particular query plan has not been benchmarked.
- **Correction:** indexed due-at on connections, durable fair account cursors, distinct thread deltas, bounded SQL windows and explicit paused/deferred message state. Apply tenant fair share across accounts before enqueueing.
- **Validation:** >1000 connected synthetic senders, >200 blocked earliest messages and large thread histories; assert bounded SQL reads and maximum scheduling delay for every eligible account.

### F14 — Database relationships have no foreign-key enforcement

- **Evidence/status:** reproduced metadata inspection: **24 tables, zero foreign keys**. Owner IDs, source links, opportunity links and document references are plain string columns (`models.py:134–195` and other models). SQLite's foreign-key PRAGMA cannot enforce constraints that do not exist. The application uses owner-scoped API queries; this finding does not demonstrate an authorization bypass.
- **User impact:** bugs, partial migrations or administrative scripts can create orphans and inconsistent/cross-owner links without database rejection.
- **Scaling impact:** repair and deletion become expensive; application-only invariants are fragile across independently evolving workers.
- **Correction:** preflight orphan/mislink report, then additive foreign keys and appropriate composite tenant constraints. Use `NOT VALID`/online validation where PostgreSQL permits. Consider RLS as defense in depth only after explicitly designing global public versus private tables and worker roles.
- **Validation:** cross-tenant fixture matrix for all private resources; invalid owner/link inserts must fail; account deletion preserves/cleans intended public and application history. Validate on PostgreSQL, not only SQLite.

### F15 — Document version allocation is racy

- **Evidence/status:** confirmed missing database invariant. [`services.py:265–269`](../backend/app/services.py#L265) computes `MAX(version) + 1`; `Document` has no matching unique scope/version constraint (`models.py:171–181`). Two transactions can read the same maximum. A concurrent PostgreSQL reproduction remains outstanding.
- **User impact:** simultaneous generation/upload can create repeated version numbers, making the history ambiguous.
- **Scaling impact:** additional document workers increase allocation collisions.
- **Correction:** lock a version-counter row per owner/document scope or allocate atomically; enforce uniqueness with explicit handling of a nullable opportunity scope. Maintain stable document IDs and downloads.
- **Validation:** concurrent PostgreSQL generation for the same scope produces unique increasing versions; different scopes do not serialize unnecessarily; failure/retry cannot overwrite an existing document.

### F16 — Concurrent identical LLM analyses miss the cache

- **Evidence/status:** reproduced five identical concurrent descriptions with a fake provider: **five model function calls**, despite concurrency=2. [`llm.py:175–185`](../backend/app/llm.py#L175) checks cache before the semaphore and never rechecks after acquiring it; cache population happens only after awaiting analysis. The cache is process-local; separate source tasks have separate semaphores.
- **User impact:** optional model usage can cost more and delay discovery without improving facts.
- **Scaling impact:** concurrent sources/processes multiply identical paid work and per-task concurrency allowances. No paid provider was contacted during reproduction.
- **Correction:** per-fingerprint singleflight, post-semaphore cache recheck, durable/shared result cache with model/prompt/extractor version, and a global provider/token budget. Keep failed analyses unverified and deterministic rejection ahead of model calls.
- **Validation:** identical concurrent inputs cause one fake provider call, unrelated descriptions remain bounded, process restart reuses valid results, and changed model/prompt invalidates correctly. Instrument actual calls/tokens/cost rather than inferring cost from listing count.

### F17 — Worker status combines incompatible worker roles

- **Evidence/status:** confirmed implementation. [`monitoring.py:8–30`](../backend/app/monitoring.py#L8) stores presence/concurrency without roles, then sums all live worker capacity. Cloud Compose runs separate discovery/application/outreach roles. A live outreach-only process can therefore make aggregate status online while no discovery capacity exists.
- **User impact:** the dashboard cannot explain a queue that is stuck because its worker role is missing.
- **Scaling impact:** aggregate capacity is misleading for autoscaling and readiness. File-heartbeat health is useful locally but does not establish multi-host worker health.
- **Correction:** heartbeat roles/build/host/capacity, role-specific freshness, oldest queued age, task throughput and lease-expiry/error metrics. Use database-backed fleet readiness; retain container-local liveness checks.
- **Validation:** start one role at a time and queue every kind; the absent roles must be unhealthy/degraded and their capacity zero. Verify monitoring itself remains cheap as worker history grows.

### F18 — Adaptive concurrency couples unrelated hosts and tenants

- **Evidence/status:** confirmed implementation. [`worker.py:36–46`](../backend/app/worker.py#L36) calculates a global recent crawl error ratio across all sources/owners; >25% errors halves each discovery worker's capacity.
- **User impact:** an outage or many invalid sources on one provider/account can slow healthy independent providers/accounts.
- **Scaling impact:** broad fleet backpressure wastes available healthy-source capacity, especially across 1000 heterogeneous sources.
- **Correction:** per-host/provider circuit breakers and bounded concurrency, tenant fairness and a separate global backstop driven by real DB/CPU/memory pressure. Preserve shared per-host rate budgets and Retry-After handling.
- **Validation:** inject failures for one host/tenant while others succeed; only affected budgets should contract. Measure recovery hysteresis and fairness; prevent retry storms on breaker reopening.

### F19 — External form preparation has no resumable browser handoff

- **Evidence/status:** confirmed capability gap. [`automation.py:159–175`](../backend/app/automation.py#L159) disables external JavaScript and blocks mutating requests; final submission is restricted to the local test endpoint. `finally:309–317` closes the context/browser. Persisted cookies/storage do not preserve filled DOM inputs or file selections. Setting an input file is not evidence of server-side upload.
- **User impact:** a screenshot/prepared answer package may be available, but opening the official URL in the user's normal browser does not continue the filled session. Dynamic/authenticated ATS forms often cannot be prepared by this path.
- **Scaling impact:** adding browser replicas does not provide missing adapter capability and unnecessarily increases browser cost if presented as universal assistance.
- **Correction:** clearly expose per-adapter capabilities and supported handoff. Prefer answer/document packages plus official-page links until a constrained, authenticated interactive handoff or permitted API adapter exists. Preserve specific-action consent and require actual receipts for submitted status.
- **Validation:** supported static form, script-only form, login, CAPTCHA, unsupported question and browser crash. Assert prepared/filled/uploaded/submitted are distinct; only authorized test receipts produce confirmed submission. No real external application is needed for these tests.

### F20 — Frontend screen state is monolithic and not normal route state

- **Evidence/status:** confirmed implementation. [`page.tsx:1,81–84`](../frontend/src/app/page.tsx#L81) places most screen orchestration in one client component with numerous shared state arrays. The screen is `useState('overview')`; screen navigation is predominantly state-based. A reload resets it and browser back/forward does not naturally traverse screen changes. Broad `Item`/`any` payloads weaken contract checking. The mobile navigation uses custom open/close state; keyboard/focus behavior needs browser validation before a WCAG failure is asserted.
- **User impact:** poor deep links/navigation continuity; unrelated resource refreshes rerender shared screen state. Large single-line JSX and global style overrides make small changes harder to review.
- **Scaling impact:** unnecessary client loading/rendering and coupling of all feature schemas; actual bundle/render timing has not been profiled in this audit.
- **Correction:** preserve visual design while splitting App Router screens under a shared authenticated layout, typed generated API contracts, feature resource hooks and lazy heavy panels. Encode shareable filters in URLs and retain private account-scoped local preferences. Use accessible dialog primitives for mobile drawers where needed.
- **Validation:** back/forward/reload/deep link tests, account-switch stale-response tests, bundle analysis/React profiling, keyboard-only mobile drawer and detail-sheet flows, reduced motion and contrast checks. No current Lighthouse/axe score is claimed.

### F21 — Migration history mixes schema evolution with an unbounded source backfill

- **Evidence/status:** confirmed implementation. [`migrate.py:11–44`](../backend/app/migrate.py#L11) runs under one transaction/advisory lock, initializes version 1 from current mutable metadata, and migration 3 loops every account with per-account source reads/inserts. It also enables those added sources. Versioned migrations and advisory locking are already present; this is not a finding that migrations are missing.
- **User impact:** upgrades on a large existing installation can wait for a long data migration; implicit enabled-source creation changes discovery configuration during schema upgrade.
- **Scaling impact:** account-proportional round trips under a global migration transaction; fresh and historically upgraded schemas are harder to compare as metadata changes.
- **Correction:** immutable migration definitions, compatibility checks, separate bounded resumable data backfills and explicit source-default policy. Use expand/backfill/validate/contract, keep migrations separate from ordinary API/worker startup once deployment orchestration is available.
- **Validation:** migrate every historical supported version to latest on PostgreSQL; compare resulting schema; interrupt/resume backfill and roll application versions without duplicate sources or permissions changing unexpectedly.

### F22 — Frontend advertises 10 MB resumes but backend accepts 8 MiB

- **Evidence/status:** confirmed implementation. [`page.tsx:233–234`](../frontend/src/app/page.tsx#L233) accepts/advertises up to 10 × 1024² bytes. [`main.py:627–635`](../backend/app/main.py#L627) reads 8 MiB + 1; `documents.py:57–58` rejects anything above 8 MiB. The body middleware is another independent bound.
- **User impact:** a file accepted by the UI fails after upload.
- **Scaling impact:** wasted upload bandwidth and parsing/error work; limited severity.
- **Correction:** one documented server capability/constant, consistent client hint and request-body/multipart allowance. Keep strict server validation.
- **Validation:** exact boundary and just-over-boundary PDF/TXT/DOCX multipart tests; verify units and visible error message.

## Defensive security risks and unresolved questions

These are not demonstrated exploits. Do not report them as confirmed breaches.

1. **DNS validation versus actual connection destination.** `discovery.py:85–94` validates DNS and public addresses; the HTTP transport subsequently resolves/connects independently. Resolve whether the deployment egress proxy pins/revalidates destination IPs and whether redirects and Playwright subrequests receive equivalent enforcement. Add controlled rebinding/redirect tests and network-level private-range deny rules. Current HTTPS/private-range/restricted-platform checks are real controls, not absent SSRF protection.
2. **Untrusted PDF resource isolation.** `documents.py:64–75` bounds file/pages/extracted text, but text limits are checked after extraction/decompression. `main.py:633` uses a thread, which supplies no hard memory/time boundary. Validate with bounded adversarial fixtures in a separate constrained process; add CPU/memory/wall-clock limits and per-account storage/processing quotas. DOCX does include zip-entry and expanded-size checks.
3. **Long-lived SSE and DB pool usage.** `main.py:730–771` polls SQL from an async stream; investigate FastAPI dependency cleanup semantics for this installed version and whether auth dependency sessions retain a pool connection for the stream lifetime. Confirm logout/account-disable behavior for already-open streams. Current payloads are refresh signals; no sensitive streamed payload leak has been demonstrated.
4. **Key rotation and disaster recovery.** `security.py:10–24` loads one Fernet key; no demonstrated multi-key rotation or tested restore process. Loss of the key makes encrypted records unreadable. Review owner access, key backups, database backups and audit-log retention together; test restore with a temporary environment and no real user exports.
5. **Tenant isolation under failure paths.** API ownership checks, owner step-up and audits exist. Absence of foreign keys/RLS is not proof they can be bypassed. Add negative tests for every endpoint, background payload and owner operation; examine connection/session scope before introducing RLS.
6. **Content security policy and frontend injection.** Inspect effective runtime headers, inline style/script requirements, React escaping and any rich HTML sink. Do not equate use of client components or inline styles with XSS. No working XSS/SQL injection was established in this audit.
7. **Provider delivery and OAuth verification.** Gmail/SMTP/Telegram/Twilio need real authorized accounts and recipient approval for live testing. Gmail OAuth consent scopes/publisher verification, revoked refresh tokens, quota errors and bounce schemas remain operational verification work. Keep ambiguous send outcomes non-retryable until reconciled.
8. **Capacity and failure-domain evidence.** No current measured 1000-source HTTP crawl, cross-host failover, long-running soak, pool saturation, rolling-upgrade or backup-restore result is established. A database task-claim benchmark is not an HTTP crawler benchmark. Docker Compose on one host is not a multi-region/distributed availability guarantee. `.github/workflows/ci.yml` defines backend Ruff/pytest (with Chromium installed) and frontend lint/typecheck/build; it does not provision an explicit PostgreSQL service or define a separate frontend responsive/accessibility/load gate. Existing browser automation unit/integration tests should not be described as absent, but their presence does not prove these production-scale properties.
9. **Eligibility coverage/calibration.** `matching.py:98–223` uses a fixed vocabulary, geography and requirement patterns. It already flags many unsupported mandatory conditions and distinguishes preferred qualifications. No specific new false-eligibility counterexample was proven here. Build a labeled, versioned India/international/2029 dataset, measure false-eligible/false-ineligible rates and keep uncertainty visible. LLM annotations must remain untrusted and candidate facts must stay outside job-only prompts.
10. **Notification automation semantics.** External notification delivery requires approval; quiet-hour deferral requires later approval. This is conservative behavior consistent with specific-action consent, but differs from fully unattended alerts. Decide any future standing-consent policy explicitly; do not remove approvals simply to match a marketing label.
11. **Storage growth.** `Document.content_encrypted` stores full blobs in relational storage (`models.py:179`). Investigate document/screenshot/session/audit/task retention and tenant byte quotas before large adoption. Encrypted object storage is an option after backup/access/deletion semantics are defined; it is not automatically a required rewrite.
12. **Dependency/security advisories.** A lockfile and versioned dependencies exist. No fresh vulnerability database scan was executed in this audit; no CVE-free claim is warranted. Validate install reproducibility, package advisories and browser sandbox support in the actual deployment image.

## Validation performed during this audit

Executed isolated diagnostics with temporary data directory, generated temporary encryption key, SQLite configuration, bytecode disabled, fake HTTP/model functions, and no external provider requests:

| Diagnostic | Actual result |
| --- | --- |
| SmartRecruiters 30 relevant postings | Returned 20; `truncated=False` — defect reproduced |
| Greenhouse unexpected HTTP 200 JSON schema | Accepted as empty complete result — defect reproduced |
| Five concurrent identical descriptions | Five fake model calls — duplicate-work defect reproduced |
| SQLAlchemy schema inspection | 24 tables; zero foreign keys — confirmed |

**Focused regression run completed: 156 passed in 26.38 seconds, exit code 0.** Executed on 2026-10-28 with the backend virtual environment:

```sh
.venv/bin/python -m pytest -q -p no:cacheprovider -o faulthandler_timeout=60 \
  tests/test_matching.py tests/test_discovery.py tests/test_llm.py \
  tests/test_opportunity_query.py
```

The command ran from `backend/` with `PYTHONDONTWRITEBYTECODE=1`, a fresh temporary data directory/SQLite URL, a temporary generated Fernet key, development configuration, disabled Redis/default LLM provider and blank external provider credentials. Network permission was enabled for the completed rerun; provider scenarios use test fixtures/mock transports. No real applications or outgoing messages were sent.

The first attempt in the more restricted execution environment was **interrupted**, exit code 2: pytest reported 131 passed and one asyncio executor thread-join warning after 434.09 seconds. It was not a completed successful run. The subsequent completed run above avoids conflating this environment shutdown stall with a proven application failure. PostgreSQL race/load behavior is still untested.

A document consistency check also executed: 22 unique finding IDs; all 27 relative source-file links resolve. Historical test artifacts in `artifacts/` are historical evidence, not newly executed validation. Existing green tests do not cover every finding above; the three counterexample probes reproduced defects outside those passing regressions.

Not executed: current full backend suite, frontend build/lint/typecheck, responsive browser/axe/Lighthouse suite, live provider delivery, external applications, production PostgreSQL race/load tests, or 1000-source HTTP benchmarks. No new performance result or deployment success is claimed.

## Recommended migration sequence and release gates

1. **Correct inventory and outbound safety first.** Implement F01/F02/F03/F04 with typed connector contracts, scan generations/fencing and exact-thread suppression. Add the counterexample/fault-injection tests before changing worker counts. Gate: stale/partial/malformed results cannot close valid jobs, and observed replies cannot receive follow-ups.
2. **Establish telemetry and remove event-loop blocking.** Address F05/F17, instrument event-loop lag, per-kind queue age, lease loss, DB checkout wait, provider latency and outcomes. Keep database tasks as the durable queue; replacing them with Redis-only tasks would discard useful guarantees without fixing the root cause. Gate: delayed providers/DB faults do not stall unrelated leases or create unfenced writes.
3. **Expand the schema without breaking existing data.** Add typed query fields, evaluation-version tables, canonical requisition aliases, source-presence generations, version counters and compatible indexes (F06/F09/F10/F14/F15). Audit existing orphans/duplicates before enforcing constraints. Use additive migrations and batched resumable backfills; keep old readers until parity is demonstrated. Gate: historical migrations, tenant invariants and dual-read comparisons pass on PostgreSQL.
4. **Make reads and UI refresh bounded.** Switch to indexed/keyset queries and compact projections, cheap summaries, versioned evaluations and targeted per-screen invalidation (F06/F07). Then split routes/contracts while preserving the current design and account epoch protection (F20/F22). Gate: query/evaluation-count budgets, navigation, keyboard/mobile checks and measured latency under concurrent ingestion.
5. **Separate shared public discovery from private account state.** Migrate subscriptions onto a permission-scoped global public source/requisition inventory (F08). Apply batched ingestion, fair per-host budgets, resumable pagination and isolated circuit breakers (F09/F11/F18). Gate: one fetch per shared source window; no private feed exposure; bounded scheduling lag for all tested tenants/providers.
6. **Bound optional providers and operations.** Add model singleflight/shared budgets, cursor-based Gmail scheduling and shared auth throttles (F12/F13/F16). Isolate untrusted parsers and establish encryption-key/restore procedures. Preserve per-message consent, send reservations and uncertain-outcome reconciliation. Gate: mocked quota/revocation/crash/opt-out cases, then explicitly authorized live provider acceptance tests.
7. **Add external application adapters incrementally.** First make manual packages/handoff usable (F19). Add one permitted adapter with explicit capability flags, recorded pre-submit evidence and an authorized test endpoint. Gate: no prepared/filled state becomes submitted without verified receipt; duplicate/restart tests remain green. Do not generalize a local test-portal success into claims about Workday/Greenhouse submissions.
8. **Prove scale before increasing claims.** Run reproducible PostgreSQL mixed workloads, multiple worker processes, >=1000 permitted-source schedules using controlled replay servers, provider-specific fault injection and multi-hour soak. Then do authorized bounded real-source verification. Record hardware, dataset, request budgets, concurrency, latency percentiles, memory, retries, duplicate rate and fairness. Test backup restore and rolling deployments before treating the service as production-ready.

## Context handoff / next implementation decisions

- User explicitly requested auditing without changing application functionality. This document is authorized; fixes are subsequent work.
- Preserve Next.js + FastAPI + PostgreSQL + Redis where practical, private candidate storage, hackathon discovery, owner step-up/auditing, explicit outbound consent, demo separation and conservative unknown eligibility.
- Never store or expose users' plaintext/recoverable login passwords. Current scrypt password handling is a control to retain.
- Do not deploy, send messages, upload documents to employers or submit real applications as part of this audit.
- Do not claim previous artifact pass counts as current checks. Do not interpret configured concurrency or synthetic task claims as proven crawl throughput.
- Unresolved: exact production proxy identity handling; synchronous pool occupancy with SSE; PostgreSQL lock/race behavior under delayed OAuth refresh; real provider capability/availability; browser handoff product requirements; shared-source privacy model; data-retention/restore/key-rotation policy.
- Highest-value next implementation slice: connector completeness/contracts plus stale-worker fencing and focused regression tests. It has clear user value, limited UI disruption, and strong interview evidence about correctness under failure.

# Phase 9 — public product preview and launch review

Verified 2026-10-29 UTC. **The public introduction and read-only demo are live. The complete account/backend service is not publicly deployed.** That remains a controlled-evaluation candidate, with important Phase 7 security/capacity gates open. No production database, personal records or secrets were published.

Subsequent bounded update: [Terms motion, public sign-in entry and real owner-issued account invitations](ACCESS_CONTROL.md). That record describes current version 5 and the latest source package; version 3 evidence below remains the original launch snapshot.

**Public URL:** https://internpilot-ai-notebook.antigravityfree101.chatgpt.site

**Demo:** https://internpilot-ai-notebook.antigravityfree101.chatgpt.site/demo

## Changes

- Original directional monogram, vector favicon, raster app icon and 1200×630 sharing artwork. Mineral neutrals, one accent, editorial typography, compact opportunity rows, consistent curved controls, responsive light/dark layouts and visible focus. No fabricated testimonials, employer endorsements, usage numbers or application successes.
- Public landing, interactive demo, privacy, terms and contact routes. Search, region/type filters, empty recovery, an application notebook and an accessible detail drawer work in the browser. Every example is explicitly fictional; no live opening links, backend requests, persisted personal data or external actions.
- Public navigation, refresh/deep links, robots and sharing metadata. Absolute URLs use the real configured HTTPS origin; unconfigured local builds do not invent one. Contact exposes a mailto only for a configured operator address; otherwise it explicitly discloses unavailable support.
- Private providers moved to a shared workspace route-group layout. Session/query-cache lifetime survives private navigation; public pages initialize no private APIs. Unknown full-app routes return 404. Historic root `?view=` links retain their destination. `/login` opens sign-in and `/register` registration; existing auth toggles remain.
- Public detail/dialog code loads on demand: full-app public page First Load JS **124→111kB** before/after the split. Single local entry observations: decoded JS **419,829→382,386 bytes**. These are build/observer readings, not field guarantees. Workspace First Load JS remains 156kB.
- Fixed private brand-mark contrast in both themes, demo labels/focus restoration, undefined accent token and an unsupported arrow glyph. Public assets are copied into both standalone Docker variants. Cloud frontend build accepts `PUBLIC_SITE_URL` and optional `PUBLIC_CONTACT_EMAIL`.
- Added static export, exact-artifact browser/Lighthouse, public HTTP asset-provenance and live browser scripts. Existing UI tests now use explicit registration and correctly distinguish sign-in after logout.
- Added a public dependency-notice inventory linked in the footer. Frontend prebuild preserves installed production and vendored license/notice files; the static export copies the reproducible generator. This addresses missing static-distribution attribution without inventing a project reuse license.

No backend schema, tenant authorization, catalog IDs or worker behavior changed. Existing data and functionality remain intact. No real applications, employer uploads or recruiter emails were sent.

## Deployment evidence and boundary

Published using the Sites plugin. `scripts/export-public.py` builds an allowlisted subset of the same public source into a separate project with `PUBLIC_DEMO_ONLY=true`. It excludes account routes/providers, API proxy, credentials, documents and database. Unavailable account links are removed at build time. Hosting remains online independently of a laptop; **this static deployment does not execute discovery workers**.

| Field | Exact returned value |
| --- | --- |
| Project | `appgprj_6ae2c5d885c88191a960d9b661648a37` |
| Audience | `public`, verified before update |
| Saved version | `appgprj_6ae2c5d885c88191a960d9b661648a37~appgver_44c7373280508191a8187092a13a1201` (version 3) |
| Pushed public-source commit | `4cf161727ebc198daa06d528cdccf69e02e20c1e` |
| Deployment | `appgdep_6ae2d01a87ec8191817636c5e4436ec2` |
| Terminal result | `succeeded`, 2026-10-29 04:48:46 UTC |
| Archive content hash | `sha256:d514be6b72d5ad455820c4b24552e6c1a8e5cea81100d4efed90bc8f24286b39` |

An unauthenticated, certificate-verifying HTTPX client subsequently fetched the public landing, all four subpages, three icons/social assets and dependency notices successfully. All **11 initial JS/CSS assets** were SHA-256 matched to the exact export. No account links appeared; sharing URLs used the real origin. [Live HTTP evidence](../artifacts/phase9-live/http.json), [exact deployment record](../artifacts/phase9-live/deployment.json).

**Live browser QA remains incomplete:** managed Chromium rejected the runtime proxy CA (`ERR_CERT_AUTHORITY_INVALID`) before rendering. Automatic approval review rejected installing that CA in the persistent browser trust store because it changes future HTTPS trust. The store remains unchanged, TLS validation was not disabled, and a user authorization question remains pending. This is a managed QA environment limitation, not evidence that the site's external TLS certificate is invalid. Screenshots are the exact export rendered **locally**, not claimed live captures.

## Executed checks

| Check | Actual result / limits |
| --- | --- |
| Backend | **533 passed, 2 skipped**, one existing deprecation warning, 201.17s pytest time; exit 0. Isolated SQLite, no live provider actions. [JUnit](../artifacts/phase9-backend.xml), [runner metadata](../artifacts/phase9-backend.json). PG variants were not rerun; Phase 7's 556-pass run is separate historical evidence. |
| Frontend | Full-app production build and public-only export passed; TypeScript, ESLint, format, five cache/transport tests and OpenAPI type drift passed. Root/demo First Load JS 111kB; workspace 156kB. |
| Public browser | **9 grouped checks passed**; five routes × two themes with zero axe violations; overflow checks at 320/360/390/768/1440px; filters/search/pipeline/empty recovery/lazy drawer focus, sign-in, icons/404 and no private API traffic. In-app UA/touch/150ms latency were simulated in Chromium, not a physical Instagram test. [Report](../artifacts/phase9-public/report.json). |
| Private workflows | **20 grouped checks passed**, 11 axe screen/theme evaluations without serious/critical violations; 320–1920px. Real local API writes, saved persistence, actual PDF generation/download, draft application queuing, source create/delete, dirty forms, keyboard navigation and account-cache isolation. [Report](../artifacts/phase9-workspace/report.json). No crawlers or provider actions enabled. |
| Exact static artifact | Three grouped checks passed: responsive landing, client navigation/filters/lazy drawer/focus/refresh, policies, private/API routes absent and no API traffic/JS exceptions. [Report](../artifacts/phase9-static/report.json). |
| Published site | Unauthenticated verified HTTPS/HTML/assets and 11 exact asset hashes passed. Live browser blocked as described above. |
| Dependencies | Latest `npm audit --omit=dev`: zero known vulnerabilities. Python dependencies unchanged; Phase 7 lock audit is prior evidence, not a Phase 9 scan. This does not establish absence of security defects. |
| Hygiene | New scripts passed fatal-error Ruff checks, frontend formatting and whitespace checks. Packaging uses a tracked-source allowlist and checksums, excluding runtime data/secrets/build output and unrelated artifacts. It is not a full history secret scan. |
| Compose / CI | Local and cloud Compose configurations passed `config --quiet` with synthetic secrets. Images were not built. CI now runs public/private browser and exact-export checks; hosted workflow execution has not been observed. |

These suites exercise controlled fixtures and actual local persistence, not independent recertification of every ATS, OAuth consent, Gmail delivery, external notifications, cloud worker or production migration. Prepared/queued applications remain distinct from submissions. Existing fixture regressions cover approvals, duplicate protection, authorized local test-endpoint submission/confirmation, rate limits, worker interruption and source failures. No real external application was performed.

## Screenshots and measured performance

[Desktop landing](../artifacts/phase9-static/desktop.png) · [Mobile landing](../artifacts/phase9-static/mobile.png) · [Mobile demo](../artifacts/phase9-static/demo-mobile.png) · [Account workspace](../artifacts/phase9-workspace/explorer-desktop.png).

Desktop/mobile renders were inspected for spacing, hierarchy, glyphs, contrast, wrapping and clipping. Automated accessibility is not screen-reader certification.

Lighthouse 13.0.1, system headless Chromium, simulated mobile throttling, gzip-compressed loopback static HTTP, no backend and no concurrent load generator. [Raw report](../artifacts/phase9-static/lighthouse-mobile.json).

| Metric | Final single-run local result |
| --- | --- |
| Performance / accessibility / best practices / SEO | **98 / 100 / 100 / 100** |
| FCP / simulated LCP | 0.90s / **1.92s** |
| Total blocking time / CLS | 128ms / **0** |

An earlier **uncompressed**, pre-lazy-drawer run scored 78 performance, 4.3s LCP, 320ms TBT, CLS 0; [baseline](../artifacts/phase9-public/lighthouse-uncompressed-v1.json). Both compression and code splitting changed; the score difference cannot be attributed solely to splitting. The initial automatic Lighthouse launch failed before headless flags were corrected; it is not counted as a passed measurement.

The preceding compressed version-2 run scored 97, LCP 1.94s and TBT 150ms. The small change in version 3 is ordinary single-run variation, not an attributed performance improvement from adding notices. No field p75, availability SLA, sustained mobile or production-scale claim. Private suite instrumentation still observed some route/form CLS >0.1 (maximum 0.224). Phase 7's **1M/25-client p95 11.74s** remains the capacity warning; no new backend capacity benchmark was run.

## Reproduction, update and rollback

Use the matching installed dependencies; no GPU or paid model required. Export to a separate disposable directory, never the repository itself.

```bash
npm --prefix frontend ci
npm --prefix frontend run build
npm --prefix frontend run typecheck
npm --prefix frontend run lint
npm --prefix frontend test
npm --prefix frontend run types:check
npm --prefix frontend run format:check
backend/.venv/bin/python scripts/run-ui-acceptance.py --public-ui
UI_ARTIFACT_DIR=artifacts/phase9-workspace backend/.venv/bin/python scripts/run-ui-acceptance.py --phase6-ui
backend/.venv/bin/python scripts/export-public.py --destination /tmp/internpilot-public --origin https://internpilot-ai-notebook.antigravityfree101.chatgpt.site
backend/.venv/bin/python scripts/verify-public-export.py --directory /tmp/internpilot-public/out --output artifacts/public-export-check
# Optional QA dependency, outside the application:
npm install --prefix /tmp/internpilot-lighthouse --no-save --ignore-scripts lighthouse@13.0.1
backend/.venv/bin/python scripts/verify-public-export.py --directory /tmp/internpilot-public/out --output artifacts/public-lighthouse --lighthouse-cli /tmp/internpilot-lighthouse/node_modules/lighthouse/cli/index.js
backend/.venv/bin/python scripts/verify-public-http.py --origin https://internpilot-ai-notebook.antigravityfree101.chatgpt.site --output artifacts/public-http.json
backend/.venv/bin/python scripts/verify-public-live.py --origin https://internpilot-ai-notebook.antigravityfree101.chatgpt.site --output artifacts/public-live
```

For provenance comparison add `--export /path/to/the/published/out` to the HTTP check. Rebuilding may change Next build hashes; compare the actual published artifact, not an unrelated rebuild.

The current Sites export project `/workspace/sites/internpilot-public/.openai/hosting.json` records the exact project ID above and `static.directory=out`. Preserve/recreate this identity on updates; do not accidentally create a new Site. Push the exact built public source, archive `.openai/hosting.json` + `out` only, save that SHA/archive, deploy preserving audience, repeat HTTP/browser checks. The packaged workflow helper was unavailable, so ordinary Git with the connector's short-lived `http_extra_header` credential synced source. Tokens remained in memory, never source, Git configuration, archives or logged command arguments. No GitHub repository publication is claimed.

Static rollback: redeploy prior saved version `appgprj_6ae2c5d885c88191a960d9b661648a37~appgver_f6e7719f93b881919cd048a54b71c0c5` (version 1), preserve public audience and verify. This changes only public assets. Full-app recovery follows [DEPLOYMENT.md](DEPLOYMENT.md), preserving original encryption keys/volumes. This phase adds no DB migration.

The updated local source archive is `dist/InternPilot-AI-release.zip`, with external `.zip.sha256` and [package evidence](../artifacts/phase9-package.json). It was generated from 305 reviewed tracked files; CRC and every SHA-256 manifest entry were actually verified. Reproduce with `python scripts/release.py --report artifacts/phase9-package.json` after staging the reviewed source. The package report is external to the archive to avoid a self-referential checksum. Third-party notice whitespace is intentionally preserved verbatim and scoped out of Git whitespace lint via `.gitattributes`; application/source whitespace checks still apply.

### Exact prerequisites for the complete public account product

1. Real operator identity/support email and policy review; configure `PUBLIC_CONTACT_EMAIL`. Keep public registration closed until ready.
2. Target VM/cloud account, persistent PostgreSQL, private Redis, domain/DNS, budget and offsite encrypted backup target. No backend provisioning credentials/resources are available in this session. Sites here hosts static pages only.
3. Verified socket/runner security boundaries, expensive-work quotas and bounded catalog capacity. External submission remains assisted/manual until independently authorized/certified adapters exist.
4. Several GB of image build headroom, clean disposable image/Compose verification, protected migrations/backfill/indexes, HTTPS/cookie/origin/monitoring validation and worker canary. Current vfs workspace has roughly 0.5GB free; no new Docker build is claimed.
5. Authorized provider OAuth/API setup and delivery/stop/bounce checks, full-size restore and sustained mixed-load/failure tests. Never replay uncertain external sends after recovery.

The full-stack VM/PostgreSQL architecture and **$40–125/month plus usage** planning allowance remain in DEPLOYMENT; this is not a provider quote or scale guarantee. The static preview uses the connected Sites entitlement; account billing/quota/retention should be checked rather than promised free forever.

## Final critical review — 15 remaining issues

These are classified gaps/limitations, not demonstrated exploits. Publishing only the isolated static preview avoids exposing the unresolved backend; it does not fix those backend issues.

| # / priority | Evidence / impact | Required correction |
| --- | --- | --- |
| 1 P0 | `discovery.py::validate_public_url`, `automation.py::_public_target`, `llm.py`: DNS preflight differs from socket/proxy resolution. Confirmed gap, exploit not attempted. | Enforce private/metadata denial at actual connector/proxy egress, including redirects/A/AAAA; test rebinding before untrusted tenants/sources. |
| 2 P0 | `automation.py`, `document_processing.py`, deployment images: no independent runner filesystem/DB-key privileges. Parser subprocess limits are not a complete sandbox. | Minimal isolated execution identity/egress/mounts and narrow artifact protocol. Keep external action workers off. |
| 3 P1 | `catalog_query.py`, legacy `main.py` matching/summary paths: measured 1M p95 11.74s/25 clients; sync and full-history work remains. | Bounded versioned matches/summaries; profile pool/event-loop/lock time; sustained mixed load. No thousands-user claim. |
| 4 P1 | No backend VM/DB/domain/backup account provisioned. Static preview cannot run discovery/accounts. | Supply infrastructure via secret handling; deploy/canary existing full stack after gates. No localhost account links. |
| 5 P1 | `/contact` reports missing operator support; preview policies disclose limitations. | Monitored operator identity/contact and policy review before public personal-data collection. |
| 6 P1 | `main.py` upload/query/storage/stream paths: shared auth admission exists, broader quotas incomplete. | Per-user concurrent-work/storage/SSE caps, trusted-proxy normalization, NAT-aware budgets and abuse tests. |
| 7 P1 | `main.py::stream_events`: max-audit timestamp hints/SQL polling lack durable replay. | Commit-ordered outbox/revisions, bounded catch-up and long-lived connection tests. |
| 8 P1 | Discovery/scheduler/tasks: shared catalog does not eliminate every per-user source evaluation/fanout. | Shared-source scheduling and bounded match fanout while preserving private source policies; measure fairness/lag. |
| 9 P1 | Backup review: only a small local restore measured; old backup may predate a successful external action. | Full-size offsite/PITR drill, matching keys/artifacts, paused recovery and receipt/suppression reconciliation. |
| 10 P1 | Provider fixtures are not live certification. No new production Gmail OAuth/delivery or real final-submit verification. | Authorized provider contract/delivery/receipt tests; unsupported submissions stay assisted/manual. |
| 11 P1 | Incomplete retention/export/erasure orchestration and independent DB tenant/FK defense; no leak demonstrated. | Retention policy, bounded deletion/export, role grants, historical constraint repair and tenant/pool tests. |
| 12 P2 | Private browser report has route/form CLS >0.1 despite functional/a11y passes. | Reserve loading geometry per feature; remeasure normal navigation. |
| 13 P2 | Docker copy/build-arg changes source-checked, not image-built; Phase 8 clean install predates public UI. | Fresh disposable image/Compose run with disk headroom, startup/assets and matching CI artifacts. Preserve user volumes. |
| 14 P2 | No physical Instagram Android/iOS, screen reader, field CWV or long soak; live Chrome blocked by proxy trust. | Authorized device/live browser tests and field monitoring; distinguish local lab evidence. |
| 15 P2 | Root reuse license undecided; bounded package scan is not full Git-history/container redistribution review. | Owner license choice, maintained notices/digests, dedicated history secret and OS/Chromium review before open-source release. |

## Verdict

**A shareable public preview is deployed and HTTP-verified.** Its exact artifact passes local interactive/mobile/accessibility checks. The functional account application remains in source and locally verified with existing workflows preserved. **An autonomous public multi-user backend is not yet production-ready.** Infrastructure and engineering gates above remain concrete work, not a declaration of completion.

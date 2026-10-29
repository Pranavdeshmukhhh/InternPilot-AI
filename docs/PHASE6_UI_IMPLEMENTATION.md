# Phase 6 product interface implementation

Status: implemented and locally verified. Source milestone: `17a8934`. Cloud/device/field validation remains separate.

## Source baseline and intent

Read actual source, `UI_UX_REDESIGN_SPEC.md`, production architecture and implementation handoff. Retained Next.js 15/React 19, Radix, Lucide, existing backend APIs, approval/credential boundaries and light/dark preference. No application data migration. Original source baseline is commit `eedcf4c` (frontend unchanged since the Phase 4/5 backend work).

Existing `scripts/run-ui-acceptance.py --studio-ui` passed on the old build; screenshots in `artifacts/phase6-before`. A second isolated build of the original source in `/tmp/internpilot-phase6-baseline/frontend` supplied measured network/resource observations using the same synthetic fixtures.

## Implemented source structure

- `app/page.tsx` redirects legacy root/view links; `app/[...workspace]/page.tsx` hosts routed features. `features/workspace/workspace.tsx` composes views and actions; original forms/approval dialogs were extracted into account, applications, automation, documents, notifications and opportunity feature modules.
- `components/layout/workspace-shell.tsx`: seven primary destinations; Explore tabs retain internships/hackathons/matches; profile, notification, owner and security routes remain accessible. Mobile navigation uses a focus-trapped Radix sheet.
- `features/workspace/provider.tsx`, `lib/api-client.ts`, `query-keys.ts`: one TanStack Query cache, account/session generation keys, cancellation, late-response rejection, cookie/CSRF preservation, active-view loading, selective mutation invalidation and coalesced SSE hints. Only a 60-second fallback when the stream is unhealthy; hidden tabs suppress it. Forms are excluded from generic event invalidation.
- `lib/generated-api-types.ts` is generated from real FastAPI OpenAPI with pinned openapi-typescript. Explicit read DTOs live in `api-types.ts` because many server response schemas are unmodelled. Profile, policy, explorer, drawer and application contracts are typed. Some unchanged admin/provider/import responses retain the isolated `legacy-types.ts` compatibility adapter; complete server response-model coverage is not claimed.
- `components/opportunity-explorer.tsx`: cached cursor API for supported chronological/simple filters, compatibility API for advanced/relevance filters, bounded pages, debounced cancellation, URL filters, applied/draft filter dialog, numeric validation and per-account preferences. Details fetch on selection; rows contain source attribution/freshness separate from eligibility and relevance. No large-list virtualization for twenty rows.
- `features/overview/overview-view.tsx`: reviews, confirmations, profile next step, known deadlines, real source/worker status and recent events. Removed decorative hero/progress ring/stat tiles.
- One active stylesheet `app/globals.css` plus semantic `styles/tokens.css`. Old theme files remain unimported. System typography, mineral neutral palette/one blue-gray accent, 16–24px surfaces, accessible controls, reduced-motion/forced-color rules and responsive layout.
- Lazy-loaded noncritical modules, command menu with actual opportunity/destination search, keyboard navigation, `/` shortcut opt-out; browser notification hook split away from its settings UI. Automation and outreach use active-view cached resources instead of their own polling loops.
- Local-only Next Web Vitals events; no analytics upload or private content telemetry. Browser harness captures actual metrics and request/resource observations, not field p75 certification.

## Meaningful corrections found during validation

- Canonical auth redirect now finishes before editable fields render, preventing lost input during the first route change.
- Filter URL synchronization no longer runs for unrelated detail URL changes.
- Profile state remains intact through generic SSE events; notification settings now receive a stable callback and update the correctly scoped settings cache.
- Successful empty DELETE responses are distinguishable from the mutation error sentinel, so source-removal dialogs can close correctly.
- Loading placeholders reserve sufficient list space; early measured CLS improved after this correction.
- Browser tests wait for a route-driven drawer to become visible before Escape; an earlier false failure pressed Escape before it opened.

## Executed final verification

- Frontend lint, TypeScript, production build, five transport/cache tests, generated OpenAPI drift check and Prettier check passed. Next reports workspace First Load JS 155kB versus original 170kB.
- Offline production-browser suite: **20 checks passed** (`artifacts/phase6-after/report.json`): cursor search/pagination, filters and reloads, save persistence, command navigation/hackathons, detail URL/back/Escape/focus, dirty forms and SSE updates, source create/delete, actual PDF generation/download, application preparation remaining queued, same-tab account isolation, owner/security screens, reduced motion and touch controls. Page Visibility was explicitly simulated because headless inactive tabs do not reliably become hidden.
- Layouts checked at 320/390/768/1024/1440/1920px; fresh coarse-pointer touch context at 390px. Axe: 11 screen/theme evaluations, zero serious/critical findings (not screen-reader certification). Explorer light/dark had no violations. Seven main feature routes plus security/owner were checked in dark mode.
- Adapted original studio smoke: **6 checks passed** (`artifacts/phase6-studio/studio-ui.json`), preserving auth, save, drawer, viewport/theme and reduced-motion regressions.
- Same-shaped isolated fixture comparison: idle requests **10 → 0 in 17 seconds**; first row **147.42 → 121.44px**; decoded JS **599,856 → 547,323 bytes**, encoded JS **171,114 → 168,094 bytes**. Local fixed-viewport explorer observers LCP 652 → 340ms, CLS 0.01623 → 0.01064. These are single-run localhost samples, not field p75 or mobile-network results. Later full-suite vitals include viewport changes and some CLS >0.1; no universal Core Web Vitals claim is made.
- Backend regression before Phase 7 source changes: **513 passed, 2 PostgreSQL-only skips, 1 warning in 184.43s**, isolated SQLite (`artifacts/phase6-backend-tests.xml`). No PostgreSQL run in Phase 6.

## Commands and artifact ownership

```
cd frontend
npm run lint
npm run typecheck
npm test
npm run types:check
npm run format:check
npm run build
cd ..
backend/.venv/bin/python scripts/run-ui-acceptance.py --phase6-ui
```

The runner starts temporary SQLite API and built Next only, without crawlers or live provider credentials. All fixtures are visibly labeled local tests. It measures explorer/detail/search/filter/save/command flows, viewports/themes, automated axe checks and keyboard behavior. `--phase6-baseline` plus `UI_TEST_FRONTEND_DIR` runs the original isolated source for comparison. Source export: `backend/.venv/bin/python scripts/export-openapi.py`; types generation: `npm run types:generate` then format generated file.

Final report must identify exact executed viewport/theme/accessibility/workflow coverage and any remaining gaps. No hosting, live-provider integration, production throughput, mobile field vitals or screen-reader certification has been performed.

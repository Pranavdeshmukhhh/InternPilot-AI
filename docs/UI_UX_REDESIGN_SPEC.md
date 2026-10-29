# InternPilot-AI: premium UI/UX redesign specification

Status: **design specification, not implemented UI**. Prepared against the actual frontend on 2026-10-28. Companion contracts: [engineering audit](ENGINEERING_AUDIT.md), [production architecture](PRODUCTION_ARCHITECTURE.md), and [ordered implementation handoff](IMPLEMENTATION_HANDOFF.md). No application, test or configuration files are changed by this document.

## 1. Product intent and preservation rules

InternPilot is a focused workspace for discovering opportunities, deciding which deserve attention, and managing accurate applications. The interface should make those decisions easy. Its visual character comes from typography, compact aligned rows, clear language and calm materials rather than decorative analytics or a marketing hero inside the application.

Preserve internship and hackathon discovery, regional/India/international filters, recommendations, saved opportunities, applications, resume history, profile verification, source configuration/review, notifications, outreach, emergency stop, account security and owner administration. Reducing navigation is not permission to delete features or data. Backend correctness gates from the audit precede redesign release.

Design rules:

- One dominant task per screen. A page can have one primary action; unrelated actions live beside their resource or in a labeled menu.
- Use seamless sections and lists. A surface has at most one visual container boundary; do not nest bordered cards inside bordered cards.
- Use 16–24 px corners for containers/sheets, smaller corners for compact controls, and pills only for navigation segments/chips. Rounding every element into a bubble is not the objective.
- Keep the list useful before opening a drawer: role, employer, region/remote scope, deadline, verification and match/review state. Full evidence belongs in details.
- Describe what the system knows, when it checked, and what it cannot do. Unknown information never becomes zero, “open,” “eligible,” “submitted” or “live.”
- No gradients, glow, decorative blobs, glass panels, simulated activity, invented counters, stock employer logos, confetti or bouncing animations. Initials are a neutral fallback, not a claim of affiliation.
- Do not clone a product's navigation, copy, iconography or layout. This system uses the existing InternPilot name and Lucide vocabulary with its own restrained hierarchy.

## 2. Existing implementation map

| Existing file | Inspect/preserve | Intended change during later implementation |
| --- | --- | --- |
| `frontend/src/app/page.tsx` | Auth/session/CSRF epoch guards; all current screen flows; `Modal`, `Field`, `Status`, `DocumentsView`, `JobDetail` and profile forms | Extract shared primitives and feature views into routed modules. Remove nine-resource global refresh and giant one-line view JSX incrementally; retain post-mutation consistency. |
| `frontend/src/app/layout.tsx` | Saved light/dark/system preference and pre-paint theme bootstrap | Keep preference compatibility, metadata and no-flash behavior; import one canonical token/component stylesheet once. |
| `frontend/src/app/globals.css`, `studio.css` | Actual imported mechanics and current neutral visual layer | Inventory selectors before replacement; migrate tokens/layout by component. Avoid another layer of increasingly specific overrides. |
| `frontend/src/app/human.css`, `premium.css` | Unimported older themes | Do not re-import. Remove only after confirming no runtime/build references and retaining needed semantics in canonical styles. |
| `frontend/src/components/opportunity-explorer.tsx` | Filters, debounced search, pagination, per-account/session preferences, stale fetch cancellation and scroll restoration | Routed filter state, compact projection queries, shared debounce/validation, stable paging and pending state. |
| `frontend/src/components/opportunity-row.tsx` | Separate save control, test-data label and opportunity selection | Typed row with useful source/freshness context, accessible sibling actions, score/eligibility separation. |
| `frontend/src/components/application-board.tsx`, `application-checklist.tsx` | Existing status vocabulary and requirements | Honest column mapping, compact detail workflow, mobile list fallback and explicit receipt/manual distinctions. |
| `frontend/src/components/outreach-view.tsx` | OAuth, drafts/approvals, sending windows and reply/status views | Three-pane desktop review where space permits; single-column mobile flow; no optimistic send success. |
| `frontend/src/components/automation-center.tsx` | Real operational data and deployment caveat | Role-aware health/freshness, effective schedules, bounded updates; source/task information moves into this section. |
| `source-manager.tsx`, `source-catalog.tsx`, `source-candidates.tsx`, `regional-discovery.tsx`, `opportunity-import.tsx` | Permitted sources, India presets, emerging publisher review and imported references | Preserve under Automation/Sources. Separate source subscriptions from shared source operations and private/global scope. |
| `notification-settings.tsx` | Channel consent, quiet hours, browser permissions and delivery outcomes | Notification inbox plus settings; external approval remains explicit and channel availability is truthful. |
| `account-security-view.tsx`, `owner-console.tsx`, `theme-toggle.tsx` | Session/password controls, owner step-up/auditing, theme | Account navigation and consistent forms. Owner tools remain role-restricted and visually distinct from personal workspace. |
| `frontend/src/components/ui/button.tsx`, `frontend/src/lib/utils.ts` | Existing cva/Slot variants and class utility | Extend existing button contracts; do not add a second competing component system. Reuse Radix Dialog already installed. |

Proposed module locations follow handoff T18–T20: `frontend/src/components/layout/` for the shell, `frontend/src/features/` for opportunity/application/document/account feature modules, `frontend/src/components/ui/` for shared `status-badge`, `field`, `empty-state`, `feedback`, `skeleton` and `drawer` primitives, and `frontend/src/styles/tokens.css` for canonical tokens. Client boundaries use `frontend/src/lib/api-client.ts`, `frontend/src/lib/query-keys.ts` and generated `frontend/src/lib/api-types.ts`; exact feature submodule names are recorded when their owning task extracts the current components. These are future files/modules, not existing functionality. Generated API types belong at the client boundary; component props must not remain `Record<string, any>`.

## 3. Information architecture and routes

Seven primary destinations keep daily work visible. Notifications and account settings are utility destinations, not equal-weight navigation rows.

| Primary navigation | Proposed route and sections | Existing functionality retained |
| --- | --- | --- |
| Overview | `/overview` | Useful next actions, recent/saved deadlines, personal progress and operational caveats |
| Explore | `/explore/internships`, `/explore/hackathons`, `/explore/matches` | Current internship/hackathon/recommended explorers and all existing filters |
| Saved | `/saved` | Saved list across opportunity kinds; existing saved items survive source removal |
| Applications | `/applications` | List/pipeline, preparation/review, confirmed history and manual tracker updates |
| Documents | `/documents` | Original upload, extraction proposals, tailored documents and version history |
| Outreach | `/outreach` | Gmail connection, contacts, drafts, review, scheduled attempts and replies |
| Automation | `/automation`; nested `/automation/sources`, `/automation/activity`, `/automation/policies` | Operational center, source catalog/candidates/regional presets/import, activity/errors, modes/limits/emergency stop |

Header notification control routes to `/notifications`. Account menu routes to `/settings/profile`, `/settings/security`, `/settings/notifications`, `/settings/appearance`, and sign out. The owner entry appears only for authorized owners and routes to `/owner`; server checks still govern access. Root redirects according to session to `/overview` or `/login`; `/register` exists only when backend registration policy permits it.

All old feature entry points receive explicit redirects/adapters; old session preference keys are read and migrated once per owner. URL query parameters encode shareable non-sensitive filters, sort and selected opportunity. Do not put candidate names, email, résumé text, OAuth tokens or secret source credentials into URLs. Back/forward closes/reopens details and restores filters/scroll; reload restores the current route. Invalid filters yield recoverable validation rather than a blank screen.

## 4. Design foundations

### Color system

Use a near-neutral mineral palette with a restrained blue-gray action accent. Warm white avoids glare; dark mode is neutral charcoal without a green/brown cast. Success, warning and danger are reserved for meaningful states. Every token is semantic; do not use a color's old implementation name such as `--teal` for an unrelated role.

| Semantic token | Light | Dark | Usage |
| --- | --- | --- | --- |
| `canvas` | `#F7F7F3` | `#171B1F` | Page/rail background |
| `surface` | `#FFFFFF` | `#1F252A` | Main list/forms/drawer |
| `surface-inset` | `#F0F1EE` | `#252D33` | Grouped controls, selected neutral area |
| `surface-hover` | `#F5F7F5` | `#29323A` | Quiet pointer hover |
| `text-primary` | `#20272D` | `#EDF0F2` | Titles/body |
| `text-secondary` | `#58636B` | `#B7C1C7` | Supporting content |
| `text-muted` | `#626F79` | `#AAB7C0` | Metadata that remains readable |
| `border-subtle` | `#DADDD8` | `#414D56` | Decorative dividers, not sole control boundaries |
| `border-control` | `#818A84` | `#72838F` | Inputs and required control boundaries |
| `action` | `#365E78` | `#A2C5DC` | Links, selected navigation, primary background |
| `on-action` | `#FFFFFF` | `#172630` | Primary action text |
| `action-soft` | `#EBF1F5` | `#283C4A` | Selected row/tab tint |
| `focus-ring` | `#365E78` | `#A2C5DC` | 2 px visible outline, 3 px offset |
| `success-text` / `success-soft` | `#32634F` / `#EAF3ED` | `#A6D4B6` / `#23372C` | Confirmed positive state |
| `warning-text` / `warning-soft` | `#805C20` / `#FBF3DE` | `#E8C57E` / `#3C3322` | Review/uncertain, not generic pending |
| `danger-text` / `danger-soft` | `#9C3F43` / `#FBECEF` | `#F0B2B6` / `#3E282C` | Failed/destructive/urgent problem |

Calculated pair contrasts for these proposed hex values: light primary text/surface 15.11:1; secondary 6.15:1; muted 5.16:1; primary button 6.93:1; control boundary/surface 3.56:1 and control boundary/inset 3.14:1. Muted text also remains above 4.5:1 on the proposed light canvas/inset/hover backgrounds. Dark equivalents: primary 13.53:1, secondary 8.45:1, primary button 8.52:1, control boundary 3.95:1. Proposed status text/soft combinations range 5.47–7.69:1. These are isolated color calculations, **not a completed accessibility audit of implemented components**. Hover, transparency, focus adjacency, disabled/read-only states, charts and actual computed styles must be tested.

No muted data below normal-text contrast just to make the screen look expensive. Decorative lines may be subtle; interactive control boundaries meet 3:1 where needed. Status always includes a text label/icon; never rely on green/red alone.

### Typography and spacing

- Retain a reliable local system sans stack: `ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif`. No font/CDN dependency, fake proprietary font or licensing assumption. Use tabular numerals for dates/counts/scores.
- Base 14 px/21 px desktop, 15 px/23 px mobile; body text can be 16 px in long detail/cover-letter reading. Normal labels 13–14 px; supporting metadata 12–13 px, never 9–10 px workflow text. Inputs at least 16 px on mobile to avoid browser zoom.
- Page title 28 px/34 px, weight 600, tracking -0.025em; mobile 24/30. Section title 17/24 weight 600. Row role title 15/21 weight 600; organization 13/18 weight 500. No 42 px application headings, uppercase kickers on every section or ultra-light body text.
- Spacing scale: 4, 8, 12, 16, 20, 24, 32, 40, 48 px. Page header to toolbar 24; toolbar to list 16; major sections 32. Align repeated headings, list content and actions to a shared baseline.
- Page gutter 32 desktop, 24 tablet, 16 mobile; content maximum 1440 px for data views and 920 px for forms/read-heavy views. Form field groups max 680 px. Use width for scanability, not oversized empty cards.
- Radii: 24 px floating rail/major sheet corner; 20 px main list surface; 16 px modest containers/dialogs; 10–12 px inputs/buttons; full radius for segmented controls/filter chips. Rows share dividers, not individual floating boxes.
- Elevation: none for normal rows/sections. Small menus/dialogs may use one subtle shadow (`0 8px 28px` at low opacity plus a 1 px border); no stacked shadows. Drawer overlay is a simple dim, never backdrop blur.
- Icons use existing Lucide at 16–18 px/1.75 stroke, 20 px in large controls; decorative icons hidden from accessibility tree. Icon-only actions have labels/tooltips and 44 px touch targets on coarse pointers.

### Density and controls

Default desktop row is approximately 88 px minimum, growing naturally for wrapped content; a compact desktop preference can reduce to 76–80 px while retaining readable text. Mobile rows are approximately 120–144 px depending on title length. Do not enforce a height that clips content at text zoom. One density preference belongs in Appearance, not a prominent control competing with filters.

Desktop buttons are 36–40 px high, primary submit/save forms 40–44 px; coarse-pointer/mobile targets at least 44 × 44 px with adequate separation. Toolbars wrap instead of shrinking controls into illegible icons. Disabled actions include a nearby reason when it affects a decision; opacity is not a substitute for an explanation.

## 5. Shell and responsive behavior

### Desktop, at least 1200 CSS px

A 216 px floating rail sits 16 px from viewport edges with 24 px corners and clear navigation grouping. Main content begins 256 px from the left. A quiet 64 px utility header contains the route title/breadcrumb, current contextual operational status, notifications and account control. Global theme is in account/settings, not another large topbar control. “Pause automation” stays reachable in the utility menu/status panel without dominating every browsing screen.

### Tablet, 768–1199 px

Use a collapsible labeled navigation drawer and full content width rather than a permanently narrow icon-only rail. Header shows menu, current destination, notifications/account. Explore retains a two-row toolbar; metadata columns collapse deliberately. Opening details uses a modal right sheet where at least 560 px remain for reading, otherwise full-width sheet.

### Mobile, below 768 px

One header with menu + page title + notification control; account is in the navigation drawer. No seven-item bottom bar or horizontal carousel of mystery icons. Drawer lists the same destinations and account sections, traps focus while open, closes on Escape/navigation and restores focus to the opener. Safe-area insets apply to sheets/sticky actions. Main content uses 16 px gutters; no viewport-wide horizontal scrolling.

Details and filter forms use full-height sheets. A bottom action area may be sticky inside the sheet, with one primary action and save/overflow; it must not cover content, keyboard input, focus outlines or system safe area. Sticky filter summaries never consume more than one line while scrolling.

At 200% zoom, switch layout naturally; at 320 CSS px remain operable with text reflow. Wide operational tables can scroll **within their labeled region**, with the first identity column preserved where useful; core opportunity/application flows must not require two-dimensional scrolling.

## 6. Explore: default information hierarchy and interaction

### Desktop wireframe (labels indicate structure, not seeded data)

```text
Explore                                      [Refresh permitted sources]
[Internships] [Hackathons] [Matches]
[Search roles, organizations, skills................] [Filters n] [Sort ▾]
[India] [Near Pune / Nagpur] [Remote] [More filters ▾]   [Clear filters]
Results / matching coverage                       Updated <time>
─────────────────────────────────────────────────────────────────────
<mark> <organization>              <source evidence>  Match <score> [Save]
       <role title>                                   <eligibility>
       <location/remote scope> · <compensation> · <deadline>
─────────────────────────────────────────────────────────────────────
<next opportunity...>
                                           [Previous] [Next results]
```

The primary header action requests a permitted refresh, not “Scan the internet.” While cooldown applies, label “Next check <time>” and expose effective cadence; repeated clicks coalesce to existing work. No count of internet opportunities unless the backend actually knows its scope/definition. If totals are cached, show the as-of context or omit them in favor of “More results available.”

Fast filter chips: India, Near me (configured cities only), Remote and closing soon. No inferred precise geolocation or hidden permission prompt. Preferences support Nagpur/Pune, India-wide and international eligibility; “Remote” does not imply “accepts Indian applicants.” A configurable local city group shows its current names. Preserve existing regional presets/source controls under Automation, not duplicate source-creation UI in each filter.

Advanced filters: company, country/city, remote scope, role/skills, stipend with currency/period, duration, graduation year/degree, eligibility, deadline, source confidence and include closed. Hackathons switch appropriate labels to prize, format, registration deadline and event dates; internships do not inherit hackathon start/end as application deadlines. All existing filters remain available even if moved into progressive disclosure. Dependent incompatible filters explain what changed; silently dropping them is prohibited.

Search and simple inputs use 250–350 ms debounce with cancellation; date/numeric ranges validate before submitting. Mobile filter sheet uses an explicit Apply button and current selection count; dismissing without Apply retains previous applied filters. Clear affects only current view's filters, not profile preferences. Filter count includes active meaningful constraints, not defaults presented as user choices.

### Opportunity row contract

- Organization/role identity has priority. Show a neutral monogram unless a trusted logo is available without third-party tracking. Role title can wrap to two lines; full value is available in details, not hover-only.
- Show location/remote restrictions, compensation if known and a concise deadline. Missing pay says “Not disclosed” in details; do not crowd every row with three unknown labels. Urgency text appears only when deadline/timezone supports it; date-only uncertainty says “Check closing time.”
- Match is `Match 84`, never `84% chance`. Uncomputed is `Match pending` or a dash with explanation, not zero. Adjacent eligibility states are independent: Eligible, Review needed, Ineligible. Unknown graduation/work authorization remains review even when relevance is high.
- Source context is compact plain text/icon: “Official listing · checked <time>” or “Reference · needs verification.” Official listing, verified URL and candidate eligibility are separate assertions. The detail explains each. A reference entry does not get a generic green verified checkmark.
- Closed/expired/stale state is explicit when included. They are excluded from current-open default results according to backend rules; a slow browser timer cannot keep an expired item visually open. Saved/history views retain them with actions appropriate to status.
- Use an `li`/`article` with a real primary link and separate sibling save control. Do not put a button inside another button or give the container a second keyboard-only click implementation. A stretched primary link can make unused row space clickable without covering save/menus. Middle-click/new-tab remains meaningful.
- Save button uses `aria-pressed`, a label including the role and pending/failed state. Saving may optimistically toggle with rollback; a failure must restore state and show a local retry. It must not open the detail drawer.
- New label means newly published only if actual publication date is known; otherwise use “Discovered recently.” Demo fixtures always display “LOCAL TEST” and stay excluded from real metrics.

### Detail drawer

Selecting an item sets `opportunity=<id>` in the current route and opens a 600–680 px right drawer (maximum 48vw when enough space remains). The list retains filters, page/cursor and scroll. Mobile uses a full-width sheet with a readable title and close control; device back closes the sheet first. Direct links load the same authorized item and useful parent context. An item no longer available/authorized produces a local explanation without leaking its contents.

Order of content:

1. Organization, role, source/kind and explicit open/closed/stale state; Save and overflow.
2. Match summary: score as relevance, eligibility and the recommended next action. Expand “Why this matches” for deterministic criteria, missing skills, unknown requirements, profile/rules version and coverage/freshness. Stale evaluation is labeled and refreshed; it cannot authorize application.
3. Compact facts: location/remote scope, compensation/prize, duration, deadline precision/timezone, published/discovered/last verified. A two-column definition list replaces a dashboard of mini-cards.
4. Requirements with quoted evidence and source links; distinguish verified official facts, deterministic extraction and unverified model interpretation. Do not render raw arbitrary HTML or imply an exact quote guarantees interpretation.
5. Description/registration details with accessible headings and “Show more” for long text, preserving find-in-page/select/copy.
6. Official application/registration destination, source evidence and attribution. Link text discloses target domain. “Open official page” is primary when external automated submission is unsupported.
7. Application preparation/checklist when applicable, existing tracker state and document options. Current application state remains distinct from listing eligibility.

Drawer footer chooses the truthful next action: open source, review eligibility, prepare documents, review upload or inspect confirmed application. A generic “Apply now” control must not imply platform submission. No duplicate call to action at every section. Focus is trapped, Escape closes, scroll is contained, and closing restores the original row's focus (or nearest surviving row/results heading).

## 7. Overview, saved and applications

### Overview

The overview is a personal work queue, not an analytics billboard. Header: “Overview” plus a compact current date/context; no motivational hero. First section is **Needs your attention**, containing real blocking approvals, unknown eligibility, failed attempts requiring reconciliation or deadlines on saved items. If empty, state that plainly; do not manufacture a task.

Second section is a short **For your next review** list (up to five ranked current items with freshness/coverage). Third section is **Upcoming** saved/application deadlines and recent confirmed activity. A quiet operational line shows last successful discovery and whether updates are delayed. Detailed source/queue metrics belong in Automation.

At most three compact inline metrics, only if backed by clearly defined real data: saved open opportunities, applications awaiting review, confirmed submissions in a selected period. Each links to the matching filtered view and includes an as-of/context definition when stale. Zero is a real zero; no data/error is an em dash plus explanation. Never synthesize a growth percentage, employer reach count or success chart from prepared applications.

Desktop can use a broad main list with a narrow upcoming column; mobile presents the same section order. Sections sit on page whitespace or one shared surface with dividers, not a grid of oversized cards. No chart unless it answers a user decision and has adequate real samples/denominator.

### Saved

Reuse explorer rows and filters. Default grouping can be Open, Needs checking, Closed/expired, with counts only from the saved collection. Keep list order stable while background data updates. Unsaving has an Undo action only if the backend supports a reversible saved-state write; failures stay visible. Existing notes/details remain in the drawer. Bulk submission, bulk messaging and new collection taxonomies are out of scope. A removed source never silently deletes private saved/application history.

### Applications

Default desktop is a compact pipeline with list toggle; mobile defaults to list grouped by stage. Stage mapping uses actual backend status and an exhaustive typed map, with an explicit unknown/review bucket instead of hiding unexpected records.

Suggested board groups: Preparing (`queued`, `preparing`, `ready`, `approved`); Review (`awaiting_review`, `needs_input`, `uncertain`, `failed`); Submitted (confirmed submissions); Progress (assessment/interview); Closed (offer/rejected/withdrawn). If current backend states differ, preserve them visibly until a compatible status migration exists. No drag-to-submit and no drag-and-drop dependency. A labeled stage action supports ordinary manual tracker changes where the backend permits it.

Application entries show employer/role, exact state, next step and relevant date. Confirmation receipt presence is visible. User-reported application/interview/offer stages are labeled “Recorded by you”; provider-confirmed events are labeled with their evidence. Manual tracking does not manufacture a provider receipt. “Approved” stays in preparation, never submitted.

Application detail presents a chronological evidence timeline, pinned answers/document versions, missing questions, required specific approvals, current attempt outcome and official destination. Screenshots are evidence for review, not confirmation. Uncertain outcome gets a prominent “Check outcome before retrying” action; ordinary Retry is absent until reconciliation permits it. Exact document upload and final submission are separate reviews. A pending request reserves space and disables only its own conflicting actions.

## 8. Documents, outreach and notifications

### Documents

Header: Documents with Upload original. An unobtrusive introduction explains that extracted suggestions require review. The original file and proposal are separate from verified profile facts. Accepted formats/size come from a shared backend capability contract; initially the server's 8 MiB limit controls, not the old UI's 10 MB copy. Client validation provides immediate feedback and server validation remains authoritative.

Use one upload region and a document library below it. Library columns: filename/purpose, opportunity/employer, version, created, action; mobile uses aligned stacked rows. Generating a tailored PDF selects an authorized current opportunity and document kind, shows which verified facts will be used, and reports queued/generated/failed truthfully. Version history is ordered and stable; simultaneous generations must not display conflicting version numbers.

Extraction proposal opens a review panel with fields and provenance, never a raw JSON block as the normal workflow. User accepts/edits/verifies facts through the existing profile rules; untouched suggestions stay unverified. Native PDF preview/download is enough; no custom PDF editor, AI design canvas or new paid rendering tool. Preserve originals and generated versions under documented retention. Deleting/retention controls only appear if implemented with compatible authorization/audit.

### Outreach

When disconnected, show Connect Gmail, needed permissions, known service availability and the fact that drafts do not send. OAuth errors/revocation show reconnect without discarding drafts. No mailbox password form and no claims of live integration merely because client credentials are configured.

Desktop review layout: narrow draft/contact list, readable message, contextual recipient/approval panel when width permits; below 1200 px use list → detail, not three cramped columns. Core sections: Drafts, Review, Scheduled/attempted, Replies. Filters/counts reflect actual server states. Replies and opt-out/bounce suppression remain visible beside recipient, with no “send anyway” shortcut.

Message review includes recipient, sender identity, subject/body, verified profile facts and source employer context, tone/signature, scheduled window/timezone, applicable gap/daily ceiling and exact action approval. Save draft is distinct from Approve/send. An approval-changing edit invalidates the approval. Provider-accepted, delivered (if actually known), bounced, failed and uncertain have distinct labels. Follow-ups require their own approved content and a fresh exact-thread check; a reply arriving after that check remains a documented cross-system race.

Daily capacity text is factual (“<remaining> of your configured ceiling; provider limits also apply”), never a gamified send target. No bulk-select-send, fabricated contacts, spam templates, tracking-pixel assumptions or spam-evasion settings. A failed/unknown send cannot become a green toast “Sent” just because the worker completed.

### Notifications

Notification icon has an unread count only when loaded; unknown count is not zero. Inbox supports all/unread, related item, actual event time, mark read and clear local errors. Group repetitive source changes/scan messages without hiding important saved deadline or application events. Opening a notification navigates to the appropriate scoped resource and gracefully handles deleted/inaccessible items.

Settings show available channels, configuration status, browser permission, quiet hours and timezone. Browser “denied” explains how to change permission rather than repeatedly prompting. External notification drafts/approvals and provider acceptance/uncertain states are visible. The existing per-delivery approval/quiet-hours behavior stays truthful; it is not labeled fully automatic delivery.

## 9. Automation, profile, account and owner workflows

### Automation

Automation is operational, not decorative. Top section names current mode and explains actual adapter capability: Discovery, Assisted preparation, or explicitly authorized supported automation. With the audited implementation external final-submit capability is unavailable. If an existing policy says auto, display “Auto mode selected · external submission unavailable” and the supported preparation behavior; do not pretend to submit or silently rewrite policy.

Show actual discovery/application/outreach worker roles independently, next checks/effective intervals, source coverage/partial status, queue age and recent relevant errors. Unknown/stale heartbeat means status unknown/stale, not live. Capacity is measured role-specific slots, not a simulated animated crawler. If running locally, explain that it stops with the host; claim laptop-off operation only for an actually deployed always-on service.

Sources tab preserves personal subscriptions, source catalog and India presets, emerged publisher review, imports, permission/scope and edit/remove. Make **your subscription** distinct from **shared source status**. Stopping a personal subscription does not promise to stop a global crawl. Private sources are clearly private; users cannot promote arbitrary private feeds by checking a public box. Reference-only data cannot inherit an official verification check.

Activity tab shows timestamp, source/task kind, outcome, duration, reason and evidence with pagination/filtering. Details are collapsed and redacted. Retry appears only when safe and eligible; cooldown/Retry-After shows next allowed time. Policies tab contains limits, reviewed modes, specific consent and emergency stop. Emergency stop remains immediately available, confirms the stopped state from the server, and explains that already accepted external requests cannot be recalled. Resuming uses an explicit review of enabled work.

### Profile and account

Profile is a small set of focused sections: Identity/contact; Education/graduation; Skills/projects/experience; Preferences/availability; Documents. Keep original resume suggestions distinct from verified user facts. Use inline validation, visible required fields and a clear Save changes action with pending/error feedback. Warn before discarding dirty edits when route/dialog navigation would lose them. Do not autosave guessed qualifications or mark the whole profile verified from one checkbox.

Preferences preserve India, Nagpur/Pune/local city groups, remote/international roles, interests and hackathons. Remote geographic scope, work authorization and unknown eligibility are editable facts with clear meaning. Profile changes explain that matches are refreshing; stale recommendations remain labeled until the new generation publishes. No completeness percentage unless its denominator is explicit and useful to the current action.

Security settings preserve current-password verification, new-password confirmation, session count/revocation and clear resulting session behavior. Account-menu sign out cancels requests, clears private caches/drawers and returns to login. Appearance includes Light, Dark, System and optional density/keyboard shortcut preferences; preserve the existing saved theme key and pre-paint behavior. Never lose unreadable text during transition.

### Authentication and owner console

Authentication uses a quiet centered form with the InternPilot wordmark, a concise purpose line, email/password, invitation when required, and permitted sign-in/register switch. No half-screen decorative story, oversized slogan or artificial testimonial. Password manager autofill works; inputs have correct autocomplete, labels and helpful errors. Registration availability is fetched truthfully; outages show Retry rather than presenting a working signup button.

Keep the owner-access disclosure visible without alarmist copy: the workspace owner may inspect account records under logged administration; passwords are not readable. Owner Console is a separate route with owner role indicator, step-up purpose/verification, search/paginated accounts, audited inspection and existing administrative controls. Sensitive actions describe affected account and scope; bulk data/password export does not exist. Do not design a recoverable-password view or expose private account details in shared metrics.

## 10. Status vocabulary and action semantics

| Concept | Correct presentation | Avoid |
| --- | --- | --- |
| Opportunity proof | Official listing / Reference / Needs verification, each with evidence and check time | One “verified” badge covering source, URL, eligibility and credentials |
| Match | Relevance score + separate eligibility + reasons/version | Percent chance, guaranteed fit, score 0 for missing evaluation |
| Freshness | Published if known; discovered and checked are separate | Relabeling a recent crawl as a newly published role |
| Time/eligibility uncertainty | Explicit missing country/grad/visa/deadline information | Inferring worldwide permission from “remote” or a precise closing hour from date-only text |
| Preparation | Draft, preparing, ready, review/approval needed | Submitted after preparing a document or setting a file input |
| Mutation | Upload reserved/completed; submission attempted/confirmed/uncertain | A single generic green success state |
| Outreach | Draft, approved, scheduled, provider accepted, bounced/uncertain/reply | Inbox-delivered without evidence or automatically retrying ambiguity |
| Tracking | Recorded by you versus provider-confirmed | Turning manually edited stages into verified submission metrics |
| Operation | Actual role progress, effective cadence and last observation | All roles healthy because one process is alive |

Toast copy reflects the completed boundary: “Saved,” “Preparation queued,” “Draft approved,” “Upload awaiting review,” or “Provider accepted message.” Use persistent inline status for uncertain/external outcomes. Do not show a success toast followed by a silently failed refresh; distinguish accepted action from stale display refresh.

## 11. Component and data contracts

These are implementation contracts, not code to copy without API integration:

| Component | Required typed inputs | Behavior/invariant |
| --- | --- | --- |
| `AppShell` | Authenticated account/role, route, theme, scoped unread state | Stable layout; private state cleared on account change; owner entry conditional |
| `PageHeader` | Title, optional short description, one primary action/context | Shared baseline, no decorative eyebrow requirement |
| `OpportunityList` | Compact items, cursor/hasMore, asOf/coverage, load/error state | Stable keys, current list retained during update, correct focus/page restoration |
| `OpportunityRow` | Role/org/kind, location/remote scope, deadline precision, compensation, source proof, evaluation state, saved/action state | No description blob; sibling save and primary link; missing values distinct |
| `MatchSummary` | score nullable, eligibility enum, evidence/reasons, expected/current versions | No false confidence; show stale/uncomputed explicitly |
| `SourceEvidence` | source kind/scope, assertion type, evidence URL, relevant checked time | Does not infer verification from feed presence or text age |
| `OpportunityDrawer` | Authorized detail, capability map, evaluation state, current application intent | Purpose-specific actions and accurate destination; URL-driven focus-safe opening |
| `ApplicationTimeline` | Attempts/receipts/manual events with time/provenance | Immutable evidence remains distinct from mutable tracker stage |
| `ApprovalReview` | Exact action/destination/answers/document checksum/version, current policy/capability | Edits invalidate review; cannot approve unsupported external submit |
| `ResourceState` | Loading, updating, empty, filtered empty, stale, error, forbidden, offline | Specific recovery; never use one empty state for failed fetch and zero results |
| `OperationStatus` | Per-role heartbeat/progress, queued age, effective cadence, asOf | Real freshness; no synthetic pulsing “live” indication |
| `Field` / `FormSection` | Explicit IDs, label, hint/error, validation state | Labels and descriptions bound to input; async error focus preserved |

Use one canonical token source imported by root layout, component styles with bounded specificity, existing Button/cva and installed Radix Dialog. Do not add a second icon set, animation framework, chart package, drag library or remote font to achieve this design. TanStack Query/generated API types follow the architecture handoff; no UI-only fake response shapes should hide missing backend contracts. Every visible action maps to a supported endpoint or a real navigation destination.

## 12. Interaction, accessibility and feedback

Keyboard rules: Tab/Shift+Tab follow visual order; Enter activates a focused link/button; Escape closes the topmost dismissible overlay; dialogs trap and restore focus; segmented controls implement native tab semantics when they behave as tabs. `Ctrl/Cmd+K` focuses opportunity search (navigating to Explore first only if explicitly implemented). `/` focuses search only outside editable controls and can be disabled immediately from shortcut help, with the same preference later visible in Appearance. Do not defer the single-character shortcut opt-out until another screen is redesigned. Do not intercept password fields, screen-reader keystrokes, composition/IME or a current modal. Show only shortcuts that actually work; a command palette is not required.

WCAG 2.2 AA is the target. Include skip-to-main, landmarks, one page H1, meaningful document title, `aria-current` navigation, linked label/hint/error, visible focus and error summaries. Never rely on hover for evidence or required actions. Tooltips appear on focus and pointer, do not replace accessible names, and avoid explaining entire eligibility solely in a tooltip. A save icon has a stateful accessible label. Count/status updates use polite live regions sparingly; every row refresh must not be announced. Destructive review uses an appropriate alert dialog with clear cancel/default focus, not a browser confirm with unclear scope.

Motion: hover/focus colors 120 ms; menus 100–140 ms; drawer 160–200 ms with a restrained ease curve. Animate opacity/transform only where useful, avoid layout reflow and staggered row entrance. `prefers-reduced-motion` removes drawer slide, shimmer, pulses and button scaling; static busy text plus `aria-busy` remains. No animation tells the user an idle worker is active.

Loading/empty/error specification:

| State | Required treatment |
| --- | --- |
| First load | Reserve likely layout, label region busy; show 3–5 simple static skeleton rows only after a brief delay if still pending. No fake score/company/metrics. |
| Background/filter update | Keep prior results and scroll; subtle “Updating results…”; stale requests cannot replace newer filters. Do not blank the whole app. |
| True empty account | Explain the missing setup/current collection and offer one relevant real action, such as verify profile/add permitted source. |
| Filtered empty | Repeat applied constraint context with Clear filters; do not claim no opportunities exist globally. |
| Source outage/partial | Preserve last-known results labeled with coverage/check time; show provider issue and next allowed check. No open/verified promotion from failed fetch. |
| Endpoint failure | Local inline reason and Retry; retain other working views. Generic raw stack traces/credential-bearing URLs are never shown. |
| Offline | Read-only stale content where safe, pending state clearly local; no pretend queued external mutation. |
| Forbidden/removed item | Explain access/unavailability without leaking private title/body; return to current list. |
| Validation failure | Preserve entered data, inline error and summary focus; do not show a toast as the only correction path. |
| Session expiry/account switch | Stop requests/streams, clear personal caches and drawer, login/redirect; no old account frame flashes. |
| Uncertain external action | Persistent review state with evidence/reconciliation path; no generic retry or optimistic success. |

## 13. Performance and API behavior visible to users

No global nine-endpoint refresh per screen. Query only active view resources plus a cheap scoped summary/unread/version resource. One authenticated SSE stream per active tab, with replay and targeted invalidation as in the architecture. Coalesce updates, pause hidden-tab polling and use the defined 30–60 second cheap fallback rather than asking every resource again. Detail data loads on selection; lists return compact projections and 20–50 items. Full descriptions, resumes, audit history and provider messages never ship in every row payload.

Navigation should preserve shell and cached private data safely, with no full-page spinner for a locally available resource. Limit speculative prefetch to one likely detail/next page after measurement. Do not introduce virtualization for a 20-row page; use it only when a measured accessible rendering requirement warrants it. Render profiling precedes broad memoization. A long description must not block save/close/navigation.

Proposed targets, not current results: p75 LCP ≤2.5 s and INP ≤200 ms on a declared midrange mobile/network profile; ordinary list API p95 ≤300 ms under the architecture workload; compressed list payload ≤100 KB for ≤50 items; no layout shift from injected operational banners into the focused control; no nine-resource timer bundle; ≤2 idle conditional requests/min excluding SSE keepalive. Report cold/warm, auth/non-auth, dataset, browser/device and error samples separately. Never substitute a screenshot for responsiveness/performance evidence.

## 14. Validation matrix and release acceptance

Run browser flows with actual API contracts on an isolated synthetic account; fixtures must be labeled in test/demo environments, never seeded as production opportunities. Visual checks complement functionality/a11y tests, not replace them.

| Dimension | Required cases |
| --- | --- |
| Viewports | 320×568, 390×844, 768×1024, 1024×768, 1440×900, 1920×1080; portrait/landscape mobile; 200% text/page zoom and reflow |
| Appearance | Light, dark, system change, reload/pre-paint, reduced motion, high-contrast/forced-colors where supported |
| Input/access | Keyboard-only, touch/coarse pointer, screen-reader smoke test; visible focus, drawer focus return after item disappears, no nested interactive elements |
| Data | No records; 1, 20, 50 per page; long names/titles/Unicode; missing salary/URL/score/deadline; date-only deadline; multiple cities; remote restricted to non-India; internship/hackathon distinctions |
| State | First load, cached update, rapid filters, empty filters, stale matches, source schema failure, 429/cooldown, offline, partial response, session expiry and account switch |
| Actions | Save/undo/rollback, open official destination, prepare/review/upload/test receipt, uncertain application; Gmail draft/edit/reapprove/reply suppression/uncertain send; stop/resume; profile dirty edit |
| Privacy | Owner/non-owner routes, unauthorized detail IDs, account cache isolation, private source name/event redaction, authenticated artifact download and active session revocation |

Release checklist:

- [ ] All seven primary destinations and utility/account routes function, with reload/back/forward and accessible page titles; every old feature has a mapped home.
- [ ] Existing user preferences, saved records, application/document history and permissions remain intact through migration. No UI-only rewrite of policy or verification state.
- [ ] New row/drawer correctly distinguishes source proof, URL check, relevance, eligibility, publication/discovery and confirmation states.
- [ ] Filters/search/pagination preserve backend semantics and cancel stale fetches; hidden/error states never fabricate empty results.
- [ ] No fake statistics/listings/activity, unsupported submit controls or provider-delivery claims. All numbers have definitions/as-of where needed.
- [ ] Desktop/mobile/screen-reader/keyboard core tasks complete; AA text/control contrast and focus verified on computed styles; zero critical/serious automated a11y issues in tested routes, with manual exceptions documented rather than silently waived.
- [ ] Background operations do not repeatedly steal focus, reorder the selected list or erase form edits. Browser back closes the detail before losing the list.
- [ ] Actual network assertions satisfy active-view fetching/fallback/SSE limits; no unauthorized outgoing action during tests.
- [ ] Upload limit copy matches backend capability; document proposals never become verified facts without review; versions and outcome labels are factual.
- [ ] Both themes cover errors, inputs, disabled/read-only controls, sheets, tables, notifications and owner screens; no old green/dark selector bleed from legacy CSS.
- [ ] Screenshots, interaction traces, network/request counts, accessibility reports and device/viewport details accompany the implementation PR. Build/typecheck/lint and relevant integration tests are executed and their actual results recorded.

## 15. Explicit exclusions and implementation boundaries

This redesign does not add a command-palette product, chat assistant, vector search, live remote desktop, résumé canvas editor, new notification provider, collection hierarchy, drag-to-submit automation, decorative analytics or another visual theme. It does not fix backend truthfulness by renaming unsupported behavior. The engineering handoff controls schema/API/worker migrations and release order; this document controls presentation, interaction and accessibility on those truthful contracts.

The acceptance targets above are proposed requirements. No implemented UI, browser accessibility pass, responsive benchmark, deployment or live provider result is claimed by this specification. Only design-token contrast calculations were executed while preparing it; full component verification belongs to later implementation.

# Studio interface — 28 October 2026

This is an in-place interface redesign. The existing discovery, matching, application consent, documents, outreach, hackathon and owner workflows keep their APIs and database schema. No package dependency, external service, default credential or database migration was added.

## Design changes

- A single product appearance layer, `frontend/src/app/studio.css`, now follows the existing workflow mechanics in `globals.css`. The earlier `human.css` and `premium.css` files remain in the source tree but are no longer imported. This avoids stacking another active color theme over them.
- Neutral white and gray surfaces, near-black text, restrained blue actions and system typography replace the ivory/teal styling. Light is the default; explicit light/dark/system preferences still work. The operating system supplies the typeface; proprietary Apple fonts or assets are not bundled.
- Larger headings and a consistent spacing scale distinguish the page, controls and content. Floating navigation, sheets, grouped rows and forms use deliberately coordinated corner radii. Status colors retain their meaning instead of coloring every label.
- The explorer puts search and filters before regional browsing and results. Source setup and the location/eligibility explanation move below the results in expandable sections. All previous source and profile controls remain reachable.
- `opportunity-row.tsx` presents employer initials, title, location, remote status, deadline, eligibility concerns, skills and the actual score. Repeated application advice stays in the detail sheet. Initials are text fallbacks, not invented employer logos.
- The bookmark is a separate, accessible action. Opening a row displays an edge-aligned opportunity sheet. Evidence, missing qualifications, source links and the existing draft/document controls remain. Escape closes it; focus returns to its opener, with a workspace fallback if the original row disappeared.
- Worker status remains factual and visible in a quieter operational notice. This does not connect, provision or simulate a worker.
- Native picker labels fit small screens; controls retain visible focus and reduced-motion support. Slide/fade transitions are bounded, and browser checks wait for closing sheets to finish before navigating.

## Preview

These images use explicitly labeled **Local test** fixtures in a temporary workspace. Test opportunities are excluded from real dashboard statistics. They are not examples of live vacancies or actual candidate eligibility.

- [Authentication](../artifacts/studio-auth.png)
- [Overview](../artifacts/studio-overview.png)
- [Desktop explorer](../artifacts/studio-explorer-desktop.png)
- [Mobile explorer](../artifacts/studio-explorer-mobile.png)
- [Dark mobile explorer](../artifacts/studio-explorer-dark.png)
- [Desktop opportunity sheet](../artifacts/studio-detail-desktop.png)
- [Mobile opportunity sheet](../artifacts/studio-detail-mobile.png)

## Reproduce

```bash
cd frontend
npm run build
cd ..
backend/.venv/bin/python scripts/run-ui-acceptance.py --studio-ui
```

On Windows use `backend\.venv\Scripts\python.exe`. The runner starts temporary local API/frontend services and closes them after the checks. This particular suite starts no crawler or application worker and sends no emails or applications. The prior regression suites remain available through the same runner.

All six browser suites passed on the final build: **67 checks** (six studio, 15 browsing/theme, seven regional, five source review, 24 existing acceptance and ten production workflows). The production build, its lint/type checks and script Ruff checks passed. Native picker labels were checked for clipping, screenshot transitions were allowed to complete, and closing-sheet navigation waits for the actual modal lifecycle.

Validation evidence is recorded in [studio-ui.json](../artifacts/studio-ui.json) and [the test report](TEST_REPORT.md). The complete backend verification from 27 October remains historical evidence; backend implementation was not changed for this interface work. Cloud hosting, provider credentials and externally certified submission adapters retain their documented setup requirements.

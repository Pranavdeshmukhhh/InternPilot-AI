'use client';
import { useState, useEffect } from 'react';

import {
  CalendarClock,
  Check,
  CircleHelp,
  Compass,
  FileCheck2,
  Pause,
  Play,
  Rocket,
  ShieldCheck,
  SlidersHorizontal,
  Square,
  Terminal,
  UserRound,
} from 'lucide-react';
import { Button } from '@/components/ui/button';

import type { Policy, Health } from '@/lib/api-types';
type Item = Partial<Policy>;
import { human } from '@/features/shared/format';
import { Field, PageTitle } from '@/features/shared/primitives';
export function PolicyView({
  initial,
  busy,
  onSave,
  onStop,
  health,
  demo,
  seed,
}: {
  initial: Item;
  busy: boolean;
  onSave: (p: Item) => Promise<void>;
  onStop: () => void;
  health: Partial<Health>;
  demo: () => Promise<unknown>;
  seed: () => Promise<unknown>;
}) {
  const [p, setP] = useState<Item>({
    deadline_reminders: true,
    deadline_reminder_hours: 48,
    deadline_minimum_score: 50,
    auto_prepare: false,
    preparation_minimum_score: 70,
    daily_preparation_limit: 10,
    ...initial,
  });
  const [demoResult, setDemoResult] = useState<unknown>(null);
  useEffect(
    () =>
      setP({
        deadline_reminders: true,
        deadline_reminder_hours: 48,
        deadline_minimum_score: 50,
        auto_prepare: false,
        preparation_minimum_score: 70,
        daily_preparation_limit: 10,
        ...initial,
      }),
    [initial],
  );
  const set = <K extends keyof Policy>(k: K, v: Policy[K]) => setP((o) => ({ ...o, [k]: v }));
  const modes = [
    {
      id: 'discovery',
      icon: Compass,
      label: 'Discovery',
      tag: 'START HERE',
      description: 'Find and rank opportunities. No application forms are prepared or submitted.',
    },
    {
      id: 'assisted',
      icon: UserRound,
      label: 'Assisted Apply',
      tag: 'REVIEW FIRST',
      description:
        'Create accurate drafts. Approve each external upload and complete the final submission yourself.',
    },
    {
      id: 'auto',
      icon: Rocket,
      label: 'Automatic drafts',
      tag: 'DRAFTS ONLY',
      description:
        'Prepare verified matches within your limits. External uploads need your approval; final external submissions stay manual.',
    },
  ];
  return (
    <>
      <PageTitle
        kicker="AUTOMATION WITH BOUNDARIES"
        title="Application policies"
        description="Choose a mode, define your limits, and keep the final say over your applications."
      />
      <form
        onSubmit={(e) => {
          e.preventDefault();
          onSave({
            ...p,
            allowed_companies: (p.allowed_companies || []).filter(Boolean),
            allowed_origins: (p.allowed_origins || []).filter(Boolean),
          });
        }}
      >
        <section className="panel policy-mode-panel">
          <div className="panel-head">
            <div>
              <h2>Application mode</h2>
              <p>Ambiguous, unsupported, or sensitive applications always pause for review.</p>
            </div>
            <ShieldCheck size={19} className="muted" />
          </div>
          <div className="mode-grid">
            {modes.map((m) => (
              <label className={`mode-card ${p.mode === m.id ? 'selected' : ''}`} key={m.id}>
                <input
                  type="radio"
                  name="mode"
                  value={m.id}
                  checked={p.mode === m.id}
                  onChange={() => setP((o) => ({ ...o, mode: m.id as Policy['mode'], auto_consent: false }))}
                />
                <div className="mode-card-top">
                  <span className="mode-icon">
                    <m.icon size={23} strokeWidth={1.7} />
                  </span>
                  <span className="mode-radio">{p.mode === m.id && <span />}</span>
                </div>
                <span className="mode-tag">{m.tag}</span>
                <h3>{m.label}</h3>
                <p>{m.description}</p>
              </label>
            ))}
          </div>
        </section>
        <div className="callout mt-6">
          <CircleHelp size={20} />
          <div>
            <strong>Platform support determines what can run.</strong>
            <p>
              Public ATS listings support discovery. The included browser submit adapter is for the authorized
              local test portal. External applications use draft preparation and require completion on the
              official site. Automatic drafts do not approve external uploads or final submissions.
            </p>
          </div>
        </div>
        <section className="panel form-section mt-6">
          <div className="form-section-intro">
            <span className="form-section-icon">
              <SlidersHorizontal size={20} />
            </span>
            <h2>Application boundaries</h2>
            <p>These gates are checked again immediately before any supported submission.</p>
          </div>
          <div className="form-grid">
            <Field label="Minimum match score" hint="A high score never overrides uncertain eligibility.">
              <input
                type="number"
                min={0}
                max={100}
                required
                value={p.minimum_score ?? 80}
                onChange={(e) => set('minimum_score', Number(e.target.value))}
              />
            </Field>
            <Field label="Daily application limit" hint="A strict cap on approved automated submissions.">
              <input
                type="number"
                min={1}
                max={50}
                required
                value={p.daily_limit ?? 5}
                onChange={(e) => set('daily_limit', Number(e.target.value))}
              />
            </Field>
            <Field
              label="Allowed employers"
              hint="One exact company name per line. Automatic preparation follows your explicit allowlist."
            >
              <textarea
                rows={4}
                value={(p.allowed_companies || []).join('\n')}
                onChange={(e) =>
                  set(
                    'allowed_companies',
                    e.target.value.split('\n').map((s) => s.trim()),
                  )
                }
                placeholder="Company name"
              />
            </Field>
            <Field
              label="Allowed application origins"
              hint="One exact HTTPS origin per line. This does not certify an adapter or authorize a platform."
            >
              <textarea
                rows={4}
                value={(p.allowed_origins || []).join('\n')}
                onChange={(e) =>
                  set(
                    'allowed_origins',
                    e.target.value.split('\n').map((s) => s.trim()),
                  )
                }
                placeholder="https://careers.example.com"
              />
            </Field>
          </div>
        </section>
        <section className="panel form-section">
          <div className="form-section-intro">
            <span className="form-section-icon">
              <FileCheck2 size={20} />
            </span>
            <h2>Automatic preparation</h2>
            <p>
              Create draft documents for strictly eligible matches. External uploads need approval for each
              application, and you complete the final submission on the official site.
            </p>
          </div>
          <div>
            <label className="check-label deadline-toggle">
              <input
                type="checkbox"
                disabled={p.mode === 'discovery'}
                checked={!!p.auto_prepare}
                onChange={(e) => set('auto_prepare', e.target.checked)}
              />
              Automatically prepare matching applications
            </label>
            {p.mode === 'discovery' && (
              <p className="field-hint preparation-note">
                Preparation is paused in Discovery mode. Choose Assisted Apply or Automatic drafts to enable
                it.
              </p>
            )}
            <div className="form-grid">
              <Field
                label="Minimum preparation match score"
                hint="A match must also have verified eligible requirements."
              >
                <input
                  type="number"
                  min={0}
                  max={100}
                  step={1}
                  required
                  disabled={p.mode === 'discovery' || !p.auto_prepare}
                  value={p.preparation_minimum_score ?? 70}
                  onChange={(e) => set('preparation_minimum_score', Number(e.target.value))}
                />
              </Field>
              <Field
                label="Daily preparation limit"
                hint="1 to 50 preparations per day. Separate from your automated submission limit."
              >
                <input
                  type="number"
                  min={1}
                  max={50}
                  step={1}
                  required
                  disabled={p.mode === 'discovery' || !p.auto_prepare}
                  value={p.daily_preparation_limit ?? 10}
                  onChange={(e) => set('daily_preparation_limit', Number(e.target.value))}
                />
              </Field>
            </div>
            <p className="field-hint">
              Uses verified profile facts and runs only while the worker is online and activity is enabled.
            </p>
          </div>
        </section>
        <section className="panel form-section">
          <div className="form-section-intro">
            <span className="form-section-icon">
              <CalendarClock size={20} />
            </span>
            <h2>Deadline reminders</h2>
            <p>Get an in-app reminder when a matching opportunity with a known deadline is closing soon.</p>
          </div>
          <div>
            <label className="check-label deadline-toggle">
              <input
                type="checkbox"
                checked={p.deadline_reminders !== false}
                onChange={(e) => set('deadline_reminders', e.target.checked)}
              />
              Enable deadline reminders
            </label>
            <div className="form-grid">
              <Field
                label="Remind me before the deadline (hours)"
                hint="Choose 1 to 168 hours before closing."
              >
                <input
                  type="number"
                  min={1}
                  max={168}
                  step={1}
                  required
                  disabled={p.deadline_reminders === false}
                  value={p.deadline_reminder_hours ?? 48}
                  onChange={(e) => set('deadline_reminder_hours', Number(e.target.value))}
                />
              </Field>
              <Field
                label="Minimum reminder match score"
                hint="Only remind me about opportunities at or above this score (0–100)."
              >
                <input
                  type="number"
                  min={0}
                  max={100}
                  step={1}
                  required
                  disabled={p.deadline_reminders === false}
                  value={p.deadline_minimum_score ?? 50}
                  onChange={(e) => set('deadline_minimum_score', Number(e.target.value))}
                />
              </Field>
            </div>
            <p className="field-hint">Reminders run while the worker is online and activity is enabled.</p>
          </div>
        </section>
        {p.mode === 'auto' && (
          <label className="consent-box auto-consent">
            <input
              type="checkbox"
              checked={!!p.auto_consent}
              onChange={(e) => set('auto_consent', e.target.checked)}
            />
            <span>
              <strong>I activate automatic draft preparation under these rules.</strong>This preference does
              not approve external uploads or final submissions. I will approve each external upload for its
              application and complete final external submissions manually. Any uncertain or sensitive
              question must pause for review.
            </span>
          </label>
        )}
        <div className="save-bar">
          <span>
            <ShieldCheck size={14} />
            Current saved mode: {human(initial.mode)}
          </span>
          <Button type="submit" disabled={busy || (p.mode === 'auto' && !p.auto_consent)}>
            <Check size={16} />
            Save application policies
          </Button>
        </div>
      </form>
      <section className="panel emergency-panel">
        <div className="emergency-icon">
          <Square size={21} />
        </div>
        <div>
          <h2>Emergency stop</h2>
          <p>Pause new discovery, preparation, and submissions. Existing records are preserved for review.</p>
        </div>
        <Button variant={initial.emergency_stop ? 'outline' : 'destructive'} disabled={busy} onClick={onStop}>
          {initial.emergency_stop ? <Play size={15} /> : <Pause size={15} />}
          {initial.emergency_stop ? 'Resume activity' : 'Stop all activity'}
        </Button>
      </section>
      {health.test_mode && (
        <section className="panel test-panel">
          <div className="panel-head">
            <div>
              <div className="eyebrow">ISOLATED TEST ENVIRONMENT</div>
              <h2>Run the local demonstration</h2>
              <p>
                Synthetic candidate facts and a local application endpoint. No real employer receives an
                application.
              </p>
            </div>
            <Terminal size={20} />
          </div>
          <div className="test-actions">
            <Button variant="outline" disabled={busy} onClick={seed}>
              Add labeled test opportunities
            </Button>
            <Button variant="outline" disabled={busy} onClick={async () => setDemoResult(await demo())}>
              <Play size={15} />
              Run local application test
            </Button>
          </div>
          {!!demoResult && <pre className="test-result">{JSON.stringify(demoResult, null, 2)}</pre>}
        </section>
      )}
    </>
  );
}

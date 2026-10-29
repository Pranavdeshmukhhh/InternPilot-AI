'use client';
import { useId, isValidElement, cloneElement, useRef, type ReactNode } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { Activity, ArrowUpRight, CheckCircle2, Compass, Radio, ShieldCheck, X } from 'lucide-react';

import type { LegacyItem as Item } from '@/lib/legacy-types';
import { timestamp, human, fmt } from '@/features/shared/format';
export function Status({ value }: { value: unknown }) {
  const v = String(value || 'unknown');
  const kind =
    /submitted|eligible|completed|ready|enabled|succeeded|healthy|^open$/.test(v) && !/ineligible/.test(v)
      ? 'good'
      : /ineligible|failed|error|stopped|closed|expired/.test(v)
        ? 'bad'
        : /review|input|uncertain|pending|running|preparing|unverified/.test(v)
          ? 'warn'
          : 'neutral';
  return (
    <span className={`badge ${kind}`}>
      <span className="badge-dot" />
      {human(v)}
    </span>
  );
}
export function Empty({
  icon: Icon = Compass,
  title,
  children,
  action,
}: {
  icon?: typeof Compass;
  title: string;
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="empty">
      <div className="empty-icon">
        <Icon size={24} strokeWidth={1.6} />
      </div>
      <h3>{title}</h3>
      <p>{children}</p>
      {action}
    </div>
  );
}
export function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  const generatedId = useId();
  const control = isValidElement<{ id?: string; 'aria-describedby'?: string }>(children) ? children : null;
  const id = control?.props.id || generatedId;
  return (
    <div className="field">
      <label className="field-label" htmlFor={id}>
        {label}
      </label>
      {control
        ? cloneElement(control, {
            id,
            'aria-describedby':
              [control.props['aria-describedby'], hint ? `${id}-hint` : undefined]
                .filter(Boolean)
                .join(' ') || undefined,
          })
        : children}
      {hint && (
        <span id={`${id}-hint`} className="field-hint">
          {hint}
        </span>
      )}
    </div>
  );
}
export function Modal({
  open,
  onClose,
  title,
  eyebrow,
  children,
  presentation = 'dialog',
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  eyebrow?: string;
  children: ReactNode;
  presentation?: 'dialog' | 'sheet';
}) {
  const opener = useRef<HTMLElement | null>(null);
  return (
    <Dialog.Root open={open} onOpenChange={(value) => !value && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="modal-overlay" />
        <Dialog.Content
          className={`modal ${presentation === 'sheet' ? 'detail-sheet' : ''}`}
          onOpenAutoFocus={() => {
            opener.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
          }}
          onCloseAutoFocus={(event) => {
            const target = opener.current?.isConnected
              ? opener.current
              : document.querySelector<HTMLElement>('main.main-content');
            if (target) {
              event.preventDefault();
              target.focus({ preventScroll: true });
            }
          }}
        >
          <div className="modal-head">
            <div>
              {eyebrow && <p className="eyebrow">{eyebrow}</p>}
              <Dialog.Title>{title}</Dialog.Title>
              <Dialog.Description className="sr-only">
                Review details and available actions.
              </Dialog.Description>
            </div>
            <Dialog.Close className="icon-btn" aria-label="Close dialog">
              <X size={20} />
            </Dialog.Close>
          </div>
          <div className="modal-body">{children}</div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
export function PageTitle({
  kicker,
  title,
  description,
  action,
}: {
  kicker: string;
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="page-title-row">
      <div>
        <div className="section-kicker">{kicker}</div>
        <h1>{title}</h1>
        <p className="page-subtitle">{description}</p>
      </div>
      {action}
    </div>
  );
}
export function WorkerSummary({ worker, onQueue }: { worker: Item; onQueue?: () => void }) {
  const online = worker.status === 'online';
  const offline = worker.status === 'offline';
  return (
    <section className="panel worker-summary">
      <div className="panel-head">
        <div>
          <h2>Automation worker</h2>
          <p>
            {online
              ? `${fmt(worker.active_workers)} active ${worker.active_workers === 1 ? 'worker' : 'workers'} · ${fmt(worker.capacity)} concurrent task slots`
              : offline
                ? 'No worker heartbeat is currently active.'
                : 'Waiting for worker status.'}
          </p>
        </div>
        <span className={`badge ${online ? 'good' : offline ? 'bad' : 'neutral'}`}>
          <span className="badge-dot" />
          {online ? 'Online' : offline ? 'Offline' : 'Checking'}
        </span>
      </div>
      <div className="worker-queue-summary">
        {[
          { label: 'Queued', value: worker.queued },
          { label: 'Running', value: worker.running },
          { label: 'Failed', value: worker.failed },
        ].map((item) => (
          <div key={item.label}>
            <strong>{fmt(item.value)}</strong>
            <span>{item.label}</span>
          </div>
        ))}
      </div>
      <p className="worker-last-seen">
        {worker.last_seen ? `Last heartbeat ${timestamp(worker.last_seen)}` : 'No worker heartbeat recorded.'}
      </p>
      {onQueue && (
        <button className="panel-link" onClick={onQueue}>
          View worker queue
          <ArrowUpRight size={15} />
        </button>
      )}
    </section>
  );
}
export function EventList({ events }: { events: Item[] }) {
  return events.length ? (
    <div className="event-list">
      {events.map((e, i) => (
        <div className="event-row" key={e.id || i}>
          <div
            className={`event-icon ${/fail|error|stop/i.test(e.kind || e.action || '') ? 'event-error' : ''}`}
          >
            {/submit|success|complete/i.test(e.kind || e.action || '') ? (
              <CheckCircle2 size={17} />
            ) : /discover|source/i.test(e.kind || e.action || '') ? (
              <Radio size={17} />
            ) : /profile|policy|consent/i.test(e.kind || e.action || '') ? (
              <ShieldCheck size={17} />
            ) : (
              <Activity size={17} />
            )}
          </div>
          <div>
            <strong>{e.title || human(e.kind || e.action || e.event_type || 'Workspace event')}</strong>
            <p>
              {typeof e.message === 'string'
                ? e.message
                : typeof e.detail === 'string'
                  ? e.detail
                  : typeof e.details === 'string'
                    ? e.details
                    : e.payload
                      ? JSON.stringify(e.payload)
                      : e.details
                        ? JSON.stringify(e.details)
                        : 'Recorded in your workspace audit log.'}
            </p>
          </div>
          <time>{timestamp(e.created_at || e.timestamp)}</time>
        </div>
      ))}
    </div>
  ) : (
    <div className="quiet-empty">
      <Activity size={19} />
      <span>No activity recorded yet. Your next action will appear here.</span>
    </div>
  );
}

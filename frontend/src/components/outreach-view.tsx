'use client';

import { useState } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { ArrowUpRight, Check, LoaderCircle, Mail, Plus, RefreshCw, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useResource } from '@/features/workspace/provider';

type Api = (path: string, method?: string, body?: unknown) => Promise<any>;
type Contact = {
  id: string;
  name: string;
  email: string;
  company: string;
  source_url: string;
  employer_fact: string;
  role: string;
  status: string;
};
type Message = {
  preview_digest: string;
  id: string;
  contact_id: string;
  status: string;
  subject: string;
  body: string;
  recipient: string;
  company: string;
  reason: string;
  sent_at: string | null;
  scheduled_at: string | null;
  provider_id: string | null;
};
type Sender = {
  enabled: boolean;
  daily_limit: number;
  gap_minutes: number;
  timezone: string;
  start_hour: number;
  end_hour: number;
  weekdays_only: boolean;
  tone: string;
  signature: string;
  subject_template: string;
  body_template: string;
  followup_days: number;
};
type Snapshot = {
  gmail_configured: boolean;
  connection: { email: string; status: string; last_sync_at: string | null } | null;
  settings: Sender;
  contacts: Contact[];
  messages: Message[];
  counts: Record<string, number>;
  replies: {
    id: string;
    kind: string;
    from: string;
    subject: string;
    excerpt: string;
    received_at: string;
  }[];
};
const emptyContact = {
  name: '',
  email: '',
  company: '',
  source_url: '',
  employer_fact: '',
  role: 'Software engineering internship',
};
const date = (value: string | null) => (value ? new Date(value).toLocaleString() : 'Not recorded');

export function OutreachView({ api, notify }: { api: Api; notify: (text: string, error?: boolean) => void }) {
  const resource = useResource<Snapshot>('/outreach');
  const data = resource.data;
  const loading = resource.isPending;
  const error = resource.error?.message || '';
  const [tab, setTab] = useState('queue');
  const [busy, setBusy] = useState(false);
  const [contactOpen, setContactOpen] = useState(false);
  const [contact, setContact] = useState(emptyContact);
  const [verified, setVerified] = useState(false);
  const [sender, setSender] = useState<Sender | null>(null);
  const [selected, setSelected] = useState<Message | null>(null);
  const [subject, setSubject] = useState('');
  const [body, setBody] = useState('');
  const [consent, setConsent] = useState(false);
  const [schedule, setSchedule] = useState('');
  const [connectOpen, setConnectOpen] = useState(false);
  const [connectConsent, setConnectConsent] = useState(false);
  const load = () => resource.refetch();
  const action = async (run: () => Promise<any>, success: string) => {
    setBusy(true);
    try {
      const result = await run();
      await load();
      notify(success);
      return result;
    } catch (reason) {
      notify(reason instanceof Error ? reason.message : 'Action failed.', true);
      return null;
    } finally {
      setBusy(false);
    }
  };
  const openMessage = (message: Message) => {
    setSelected(message);
    setSubject(message.subject);
    setBody(message.body);
    setConsent(false);
    setSchedule('');
  };
  const draft = (target: Contact, parent?: string) =>
    action(
      () => api('/outreach/messages', 'POST', { contact_id: target.id, parent_id: parent || null }),
      'Draft created. No message sent.',
    ).then((result) => {
      if (result) openMessage(result);
    });
  const dialog = (open: boolean, close: () => void, title: string, children: React.ReactNode) => (
    <Dialog.Root open={open} onOpenChange={(value) => !value && close()}>
      <Dialog.Portal>
        <Dialog.Overlay className="modal-overlay" />
        <Dialog.Content className="modal">
          <div className="modal-head">
            <div>
              <Dialog.Title asChild>
                <h2>{title}</h2>
              </Dialog.Title>
              <Dialog.Description className="sr-only">
                Review this outreach action and its exact details.
              </Dialog.Description>
            </div>
            <Dialog.Close className="icon-btn" aria-label="Close dialog">
              <X size={18} />
            </Dialog.Close>
          </div>
          <div className="modal-body">{children}</div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
  if (loading)
    return (
      <div className="loading-panel">
        <LoaderCircle className="spin" size={24} />
        <p>Opening outreach…</p>
      </div>
    );
  if (!data)
    return (
      <div className="banner danger" role="alert">
        {error}
        <button onClick={load}>Retry</button>
      </div>
    );
  const connected = data.connection?.status === 'connected';
  const editable = selected && ['draft', 'needs_review', 'approved'].includes(selected.status);
  const changed = selected && (subject !== selected.subject || body !== selected.body);
  const pending = data.messages.filter((message) =>
    ['draft', 'approved', 'needs_review', 'uncertain', 'sending'].includes(message.status),
  );
  return (
    <>
      <div className="page-title-row">
        <div>
          <h1>Recruiter outreach</h1>
          <p className="page-subtitle">Thoughtful introductions. Every message reviewed.</p>
        </div>
        <Button
          onClick={() => {
            setContact(emptyContact);
            setVerified(false);
            setContactOpen(true);
          }}
        >
          <Plus size={16} />
          Add contact
        </Button>
      </div>
      {error && (
        <p className="banner danger" role="alert">
          {error}
        </p>
      )}
      <div className="operation-metrics">
        <div>
          <strong>{data.counts.draft || 0}</strong>
          <span>Drafts</span>
        </div>
        <div>
          <strong>{data.counts.approved || 0}</strong>
          <span>Scheduled</span>
        </div>
        <div>
          <strong>{data.counts.sent || 0}</strong>
          <span>Accepted by Gmail</span>
        </div>
        <div>
          <strong>{data.replies.length}</strong>
          <span>Recent replies & notices</span>
        </div>
      </div>
      <div className="split-heading">
        <div>
          <strong>{connected ? data.connection?.email : 'Gmail is not connected'}</strong>
          <p className="footnote">
            {connected
              ? `Last reply check: ${date(data.connection?.last_sync_at || null)}. Sending ${data.settings.enabled ? 'enabled' : 'paused'}.`
              : data.gmail_configured
                ? 'Connect your account to schedule approved messages and track replies.'
                : 'Server setup needed: Gmail OAuth client ID, secret and redirect URI.'}
          </p>
        </div>
        <div className="inline-actions">
          {connected ? (
            <>
              <Button
                variant="outline"
                size="sm"
                disabled={busy}
                onClick={() =>
                  action(() => api('/outreach/sync', 'POST', { consent: true }), 'Reply check queued.')
                }
              >
                <RefreshCw size={14} />
                Check replies
              </Button>
              <Button
                variant="ghost"
                size="sm"
                disabled={busy}
                onClick={() =>
                  action(
                    () => api('/outreach/gmail', 'DELETE', { consent: true }),
                    'Gmail disconnected. Local tokens removed.',
                  )
                }
              >
                Disconnect
              </Button>
            </>
          ) : (
            <Button
              variant="outline"
              disabled={!data.gmail_configured || busy}
              onClick={() => {
                setConnectConsent(false);
                setConnectOpen(true);
              }}
            >
              <Mail size={15} />
              Connect Gmail
            </Button>
          )}
        </div>
      </div>
      <div className="tabs-line">
        {[
          ['queue', 'Review queue'],
          ['contacts', 'Contacts'],
          ['replies', 'Replies'],
          ['sender', 'Sender settings'],
        ].map(([id, label]) => (
          <button
            key={id}
            className={tab === id ? 'selected' : ''}
            onClick={() => {
              setTab(id);
              if (id === 'sender') setSender(data.settings);
            }}
          >
            {label}
          </button>
        ))}
      </div>
      {tab === 'queue' &&
        (data.messages.length ? (
          <div className="quiet-table-wrap">
            <table className="quiet-table">
              <thead>
                <tr>
                  <th>Message</th>
                  <th>Status</th>
                  <th>Schedule / receipt</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {data.messages.map((message) => (
                  <tr key={message.id}>
                    <td>
                      <strong>{message.subject}</strong>
                      <small>{message.recipient}</small>
                    </td>
                    <td>{message.status.replaceAll('_', ' ')}</td>
                    <td>
                      <small>
                        {message.status === 'sent'
                          ? `Gmail receipt ${message.provider_id}`
                          : message.scheduled_at
                            ? date(message.scheduled_at)
                            : 'Awaiting review'}
                      </small>
                    </td>
                    <td>
                      <Button variant="ghost" size="sm" onClick={() => openMessage(message)}>
                        Open
                        <ArrowUpRight size={13} />
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="outreach-empty">
            <Mail size={24} className="mx-auto mb-4" />
            <p>Add a verified contact and generate a factual introduction.</p>
            <p className="footnote">Your verified name and at least one verified project are required.</p>
          </div>
        ))}
      {tab === 'contacts' &&
        (data.contacts.length ? (
          <div className="quiet-table-wrap">
            <table className="quiet-table">
              <thead>
                <tr>
                  <th>Contact</th>
                  <th>Company</th>
                  <th>Source</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {data.contacts.map((target) => (
                  <tr key={target.id}>
                    <td>
                      <strong>{target.name}</strong>
                      <small>
                        {target.email} · {target.status.replaceAll('_', ' ')}
                      </small>
                    </td>
                    <td>
                      {target.company}
                      <small>{target.role}</small>
                    </td>
                    <td>
                      <a href={target.source_url} target="_blank" rel="noopener noreferrer">
                        Verified source
                        <ArrowUpRight size={12} className="inline" />
                      </a>
                    </td>
                    <td>
                      <div className="inline-actions">
                        <Button
                          variant="outline"
                          size="sm"
                          disabled={
                            busy ||
                            target.status !== 'active' ||
                            pending.some((message) => message.contact_id === target.id)
                          }
                          onClick={() => draft(target)}
                        >
                          Draft email
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          disabled={busy || target.status !== 'active'}
                          onClick={() =>
                            action(
                              () => api(`/outreach/contacts/${target.id}/opt-out`, 'POST'),
                              'Contact opted out. Pending messages cancelled.',
                            )
                          }
                        >
                          Opt out
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="outreach-empty">
            No contacts saved. Add people whose recruiting role and address you have verified.
          </p>
        ))}
      {tab === 'replies' &&
        (data.replies.length ? (
          <div className="operational-list">
            {data.replies.map((reply) => (
              <div key={reply.id}>
                <div>
                  <strong>{reply.subject || reply.kind.replaceAll('_', ' ')}</strong>
                  <small>
                    {reply.from} · {date(reply.received_at)}
                  </small>
                  <p className="mail-preview">{reply.excerpt}</p>
                </div>
                <span>{reply.kind.replaceAll('_', ' ')}</span>
              </div>
            ))}
          </div>
        ) : (
          <p className="outreach-empty">No replies or delivery notices have been recorded.</p>
        ))}
      {tab === 'sender' && sender && (
        <form
          onSubmit={async (event) => {
            event.preventDefault();
            const result = await action(
              () => api('/outreach/settings', 'PUT', sender),
              'Sender settings saved. Individual approvals remain required.',
            );
            if (result) setSender(result);
          }}
        >
          <div className="outreach-editor">
            <div>
              <h2>Sending policy</h2>
              <p className="footnote">
                Gmail handles account authentication. For a custom domain, configure SPF, DKIM and DMARC with
                your mail provider. Provider quotas may be lower than this limit.
              </p>
              <label className="check-label">
                <input
                  type="checkbox"
                  checked={sender.enabled}
                  disabled={!connected}
                  onChange={(event) => setSender({ ...sender, enabled: event.target.checked })}
                />
                Enable approved scheduled messages
              </label>
              <div className="form-grid mt-6">
                <label className="field">
                  <span className="field-label">Daily maximum</span>
                  <input
                    type="number"
                    min={1}
                    max={40}
                    value={sender.daily_limit}
                    onChange={(event) => setSender({ ...sender, daily_limit: +event.target.value })}
                  />
                </label>
                <label className="field">
                  <span className="field-label">Minimum gap (minutes)</span>
                  <input
                    type="number"
                    min={10}
                    max={1440}
                    value={sender.gap_minutes}
                    onChange={(event) => setSender({ ...sender, gap_minutes: +event.target.value })}
                  />
                </label>
                <label className="field">
                  <span className="field-label">Start hour</span>
                  <input
                    type="number"
                    min={0}
                    max={23}
                    value={sender.start_hour}
                    onChange={(event) => setSender({ ...sender, start_hour: +event.target.value })}
                  />
                </label>
                <label className="field">
                  <span className="field-label">End hour</span>
                  <input
                    type="number"
                    min={1}
                    max={24}
                    value={sender.end_hour}
                    onChange={(event) => setSender({ ...sender, end_hour: +event.target.value })}
                  />
                </label>
                <label className="field">
                  <span className="field-label">Timezone</span>
                  <input
                    value={sender.timezone}
                    onChange={(event) => setSender({ ...sender, timezone: event.target.value })}
                  />
                </label>
                <label className="field">
                  <span className="field-label">Follow-up after (days)</span>
                  <input
                    type="number"
                    min={3}
                    max={30}
                    value={sender.followup_days}
                    onChange={(event) => setSender({ ...sender, followup_days: +event.target.value })}
                  />
                </label>
              </div>
              <label className="check-label">
                <input
                  type="checkbox"
                  checked={sender.weekdays_only}
                  onChange={(event) => setSender({ ...sender, weekdays_only: event.target.checked })}
                />
                Weekdays only
              </label>
            </div>
            <div>
              <h2>Writing preferences</h2>
              <label className="field mt-6">
                <span className="field-label">Tone</span>
                <select
                  value={sender.tone}
                  onChange={(event) => setSender({ ...sender, tone: event.target.value })}
                >
                  <option value="concise">Concise</option>
                  <option value="friendly">Friendly</option>
                  <option value="formal">Formal</option>
                </select>
              </label>
              <label className="field">
                <span className="field-label">Signature</span>
                <textarea
                  aria-label="Signature"
                  value={sender.signature}
                  onChange={(event) => setSender({ ...sender, signature: event.target.value })}
                  placeholder="Defaults to your verified name"
                />
              </label>
              <details>
                <summary className="text-link">Templates</summary>
                <p className="footnote">
                  Factual placeholders:{' '}
                  {'{name}, {contact_name}, {company}, {role}, {project}, {project_summary}, {employer_fact}'}
                  .
                </p>
                <label className="field">
                  <span className="field-label">Subject template</span>
                  <input
                    maxLength={200}
                    value={sender.subject_template}
                    onChange={(event) => setSender({ ...sender, subject_template: event.target.value })}
                  />
                </label>
                <label className="field">
                  <span className="field-label">Body template</span>
                  <textarea
                    aria-label="Body template"
                    value={sender.body_template}
                    onChange={(event) => setSender({ ...sender, body_template: event.target.value })}
                  />
                </label>
              </details>
            </div>
          </div>
          <Button type="submit" disabled={busy}>
            <Check size={15} />
            Save sender settings
          </Button>
        </form>
      )}
      {dialog(
        contactOpen,
        () => setContactOpen(false),
        'Add a recruiter',
        <form
          onSubmit={async (event) => {
            event.preventDefault();
            const result = await action(
              () => api('/outreach/contacts', 'POST', { ...contact, verified }),
              'Verified contact saved.',
            );
            if (result) setContactOpen(false);
          }}
        >
          <div className="form-grid">
            {[
              ['name', 'Contact name'],
              ['email', 'Recruiter email'],
              ['company', 'Company'],
              ['role', 'Relevant role'],
              ['source_url', 'Contact source URL'],
            ].map(([key, label]) => (
              <label className="field" key={key}>
                <span className="field-label">{label}</span>
                <input
                  required
                  type={key === 'email' ? 'email' : key === 'source_url' ? 'url' : 'text'}
                  value={contact[key as keyof typeof contact]}
                  onChange={(event) => setContact({ ...contact, [key]: event.target.value })}
                />
              </label>
            ))}
          </div>
          <label className="field">
            <span className="field-label">Verified employer context (optional)</span>
            <textarea
              maxLength={500}
              rows={3}
              value={contact.employer_fact}
              onChange={(event) => setContact({ ...contact, employer_fact: event.target.value })}
              placeholder="A factual reason this employer is relevant to you"
            />
          </label>
          <label className="check-label">
            <input
              type="checkbox"
              checked={verified}
              onChange={(event) => setVerified(event.target.checked)}
            />
            I verified the address, recruiting relevance and factual context from this source.
          </label>
          <Button className="mt-6" type="submit" disabled={busy || !verified}>
            Save contact
          </Button>
        </form>,
      )}
      {dialog(
        connectOpen,
        () => setConnectOpen(false),
        'Connect Gmail',
        <>
          <p className="job-description">
            Google will request permission to send approved messages and read your known outreach threads for
            replies, bounces and opt-outs. Offline tokens stay encrypted on the server. This action sends no
            email.
          </p>
          <label className="consent-box mt-6">
            <input
              type="checkbox"
              checked={connectConsent}
              onChange={(event) => setConnectConsent(event.target.checked)}
            />
            <span>
              I authorize connecting this Gmail account for sending reviewed messages and tracking replies.
            </span>
          </label>
          <Button
            disabled={!connectConsent || busy}
            onClick={async () => {
              const result = await action(
                () => api('/outreach/gmail/connect', 'POST', { consent: true }),
                'Opening Google authorization.',
              );
              if (result && new URL(result.authorization_url).origin === 'https://accounts.google.com')
                window.location.assign(result.authorization_url);
            }}
          >
            Continue to Google
            <ArrowUpRight size={15} />
          </Button>
        </>,
      )}
      {dialog(
        !!selected,
        () => setSelected(null),
        selected?.status === 'sent' ? 'Sent message' : 'Review message',
        selected && (
          <>
            <p className="footnote">
              To {selected.recipient} · {selected.status.replaceAll('_', ' ')}
            </p>
            {editable ? (
              <>
                <label className="field">
                  <span className="field-label">Subject</span>
                  <input
                    maxLength={200}
                    value={subject}
                    onChange={(event) => {
                      setSubject(event.target.value);
                      setConsent(false);
                    }}
                  />
                </label>
                <label className="field">
                  <span className="field-label">Email body</span>
                  <textarea
                    aria-label="Email body"
                    rows={13}
                    value={body}
                    onChange={(event) => {
                      setBody(event.target.value);
                      setConsent(false);
                    }}
                  />
                </label>
                <label className="check-label">
                  <input
                    type="checkbox"
                    checked={consent}
                    onChange={(event) => setConsent(event.target.checked)}
                  />
                  I reviewed this exact recipient and message; all candidate and employer claims are accurate.
                </label>
                {changed ? (
                  <Button
                    className="mt-6"
                    disabled={!consent || busy}
                    onClick={async () => {
                      const result = await action(
                        () =>
                          api(`/outreach/messages/${selected.id}`, 'PUT', {
                            subject,
                            body,
                            facts_verified: true,
                          }),
                        'Draft saved. Review again before approval.',
                      );
                      if (result) openMessage(result);
                    }}
                  >
                    Save reviewed draft
                  </Button>
                ) : (
                  <>
                    <label className="field mt-6">
                      <span className="field-label">Send after (optional, your local time)</span>
                      <input
                        type="datetime-local"
                        value={schedule}
                        onChange={(event) => setSchedule(event.target.value)}
                      />
                    </label>
                    <div className="inline-actions">
                      <Button
                        disabled={!consent || !connected || busy}
                        onClick={async () => {
                          const result = await action(
                            () =>
                              api(`/outreach/messages/${selected.id}/approve`, 'POST', {
                                consent: true,
                                preview_digest: selected.preview_digest,
                                scheduled_at: schedule ? new Date(schedule).toISOString() : null,
                              }),
                            'Specific message approved. Sender policy and reply checks still apply.',
                          );
                          if (result) setSelected(null);
                        }}
                      >
                        Approve & queue
                      </Button>
                      <Button
                        variant="outline"
                        disabled={busy}
                        onClick={async () => {
                          const result = await action(
                            () => api(`/outreach/messages/${selected.id}/cancel`, 'POST'),
                            'Message cancelled.',
                          );
                          if (result) setSelected(null);
                        }}
                      >
                        Cancel message
                      </Button>
                    </div>
                    <p className="footnote">
                      {data.settings.enabled
                        ? 'Daily limits and sending windows apply.'
                        : 'Scheduled sending is paused in Sender settings.'}
                    </p>
                  </>
                )}
              </>
            ) : (
              <>
                <h3>{selected.subject}</h3>
                <div className="mail-preview">{selected.body}</div>
                <p className="footnote">{selected.reason}</p>
                {selected.status === 'uncertain' && (
                  <Button
                    disabled={busy}
                    onClick={async () => {
                      const result = await action(
                        () => api(`/outreach/messages/${selected.id}/reconcile`, 'POST', { consent: true }),
                        'Gmail receipt check completed; inspect the recorded result.',
                      );
                      if (result) {
                        setSelected(null);
                      }
                    }}
                  >
                    Check sent receipt
                  </Button>
                )}
                {selected.status === 'sent' &&
                  data.contacts.find((target) => target.id === selected.contact_id)?.status === 'active' && (
                    <Button
                      variant="outline"
                      disabled={
                        busy ||
                        !selected.sent_at ||
                        Date.now() - new Date(selected.sent_at).getTime() <
                          data.settings.followup_days * 86400000
                      }
                      onClick={() => {
                        const target = data.contacts.find((target) => target.id === selected.contact_id);
                        if (target) draft(target, selected.id);
                      }}
                    >
                      Draft follow-up
                    </Button>
                  )}
              </>
            )}
          </>
        ),
      )}
    </>
  );
}

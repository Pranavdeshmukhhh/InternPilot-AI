'use client';

import { useCallback, useEffect, useState, type FormEvent } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { ArrowDownToLine, Database, LoaderCircle, RefreshCw, ShieldCheck, X } from 'lucide-react';
import { Button } from '@/components/ui/button';

type Row = Record<string, any>;
type Api = (path: string, method?: string, body?: unknown) => Promise<any>;
type Review = { user: Row; action: 'inspect' | 'status' | 'revoke' | 'password' | 'download'; document?: Row };
const labels = { inspect: 'View account records', status: 'Change account access', revoke: 'Sign out account sessions', password: 'Set a replacement password', download: 'Download account document' };
function date(value: string) { return value ? new Date(value).toLocaleString() : 'Not recorded'; }

export function OwnerConsole({ api, download, notify }: { api: Api; download: (path: string, body: unknown) => Promise<Blob>; notify: (message: string, error?: boolean) => void }) {
  const [overview, setOverview] = useState<Row | null>(null);
  const [directory, setDirectory] = useState<Row>({ items: [], total: 0 });
  const [search, setSearch] = useState(''); const [query, setQuery] = useState(''); const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true); const [error, setError] = useState(''); const [revision, setRevision] = useState(0);
  const [review, setReview] = useState<Review | null>(null); const [detail, setDetail] = useState<Row | null>(null);
  const [password, setPassword] = useState(''); const [purpose, setPurpose] = useState(''); const [consent, setConsent] = useState(false);
  const [replacement, setReplacement] = useState(''); const [confirmation, setConfirmation] = useState(''); const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState(''); const [audit, setAudit] = useState<Row[]>([]);
  useEffect(() => { const timer = setTimeout(() => { setQuery(search.trim()); setPage(1); }, 300); return () => clearTimeout(timer); }, [search]);
  useEffect(() => {
    let current = true; setLoading(true);
    const params = new URLSearchParams({ search: query, page: String(page), page_size: '20' });
    Promise.all([api('/owner/overview'), api(`/owner/users?${params}`), api('/owner/audit')]).then(([summary, users, trail]) => {
      if (current) { setOverview(summary); setDirectory(users); setAudit(trail); setError(''); }
    }).catch(reason => { if (current) setError(reason.message); }).finally(() => { if (current) setLoading(false); });
    return () => { current = false; };
  }, [api, query, page, revision]);
  const close = useCallback(() => { setReview(null); setPassword(''); setReplacement(''); setConfirmation(''); setPurpose(''); setConsent(false); setActionError(''); }, []);
  const open = (value: Review) => { close(); setReview(value); };
  const submit = async (event: FormEvent) => {
    event.preventDefault(); if (!review) return;
    if (review.action === 'password' && replacement !== confirmation) { setActionError('The replacement passwords do not match.'); return; }
    setBusy(true); setActionError('');
    const base = `/owner/users/${review.user.id}`;
    const body = { current_password: password, purpose, consent };
    try {
      if (review.action === 'download' && review.document) {
        const blob = await download(`${base}/documents/${review.document.id}/download`, body);
        const link = document.createElement('a'); const objectUrl = URL.createObjectURL(blob);
        link.href = objectUrl; link.download = review.document.filename; link.click(); setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
      } else if (review.action === 'inspect') setDetail(await api(`${base}/inspect`, 'POST', body));
      else if (review.action === 'status') await api(`${base}/status`, 'POST', { ...body, disabled: !review.user.disabled });
      else if (review.action === 'revoke') await api(`${base}/sessions/revoke`, 'POST', body);
      else if (review.action === 'password') await api(`${base}/password`, 'POST', { ...body, new_password: replacement });
      notify(review.action === 'password' ? 'Replacement password set. Sessions revoked and automation paused.' : 'Owner action completed and recorded in the audit trail.');
      close(); setRevision(value => value + 1);
    } catch (reason) { setActionError((reason as Error).message); }
    finally { setBusy(false); }
  };
  return <>
    <div className="page-title-row"><div><h1>Owner’s desk</h1><p className="page-subtitle">Registered accounts, stored records, and access controls.</p></div><Button variant="outline" onClick={() => setRevision(value => value + 1)} disabled={loading}><RefreshCw size={16} className={loading ? 'spin' : ''} />Refresh</Button></div>
    <div className="owner-access-note"><ShieldCheck size={20} /><p>Access to private records is logged and requires your password again. Existing passwords, password hashes, tokens, browser sessions, and the custom-answer vault are never shown.</p></div>
    {error && <div className="banner danger" role="alert">{error}</div>}
    <section className="panel owner-database"><div className="panel-head"><div><h2>Database overview</h2><p>Live row counts from this installation.</p></div><Database size={20} /></div><dl className="owner-counts">{Object.entries(overview?.tables || {}).map(([table, count]) => <div key={table}><dt>{table.replaceAll('_', ' ')}</dt><dd>{String(count)}</dd></div>)}</dl></section>
    <section className="panel mt-6"><div className="panel-head"><div><h2>Accounts</h2><p>{directory.total} registered accounts · recent visits reflect authenticated use.</p></div></div><div className="owner-search"><label className="field"><span className="field-label">Find account by email or ID</span><input type="search" value={search} onChange={event => setSearch(event.target.value)} placeholder="Email address or account ID" /></label></div>
      <div className="table-scroll"><table className="owner-users"><thead><tr><th>Account / ID</th><th>Access</th><th>Last sign-in / visit</th><th>Manage</th></tr></thead><tbody>{directory.items.map((user: Row) => <tr key={user.id}><td><strong>{user.email}</strong><small className="mono">{user.id}</small></td><td>{user.role}{user.disabled && <small>Disabled</small>}</td><td>{date(user.last_login_at)}<small>Last seen: {date(user.last_seen_at)}</small></td><td><div className="owner-row-actions"><Button variant="outline" size="sm" onClick={() => open({ user, action: 'inspect' })}>View records</Button>{user.role !== 'owner' && <><button className="text-link" onClick={() => open({ user, action: 'status' })}>{user.disabled ? 'Enable account' : 'Disable account'}</button><button className="text-link" onClick={() => open({ user, action: 'revoke' })}>Sign out sessions</button><button className="text-link" onClick={() => open({ user, action: 'password' })}>Reset password</button></>}</div></td></tr>)}</tbody></table></div>
      {!directory.items.length && <div className="quiet-empty">{loading ? 'Loading accounts…' : 'No accounts match this search.'}</div>}
      {directory.total > 20 && <div className="pagination"><Button variant="outline" disabled={page === 1 || loading} onClick={() => setPage(value => value - 1)}>Previous</Button><span>Page {page} of {Math.ceil(directory.total / 20)}</span><Button variant="outline" disabled={page * 20 >= directory.total || loading} onClick={() => setPage(value => value + 1)}>Next</Button></div>}
    </section>
    {detail && <section className="panel mt-6"><div className="panel-head"><div><h2>Account records · {detail.account.email}</h2><p>Up to 200 recent applications and documents; credential material is excluded.</p></div><button className="icon-btn" aria-label="Close account records" onClick={() => setDetail(null)}><X size={18} /></button></div><div className="owner-records"><h3>Candidate profile</h3><pre>{JSON.stringify(detail.profile, null, 2)}</pre><h3>Applications</h3>{detail.applications.length ? <ul>{detail.applications.map((application: Row) => <li key={application.id}><span className="mono">{application.id}</span> · {application.status}<p>{application.reason}</p></li>)}</ul> : <p>No applications recorded.</p>}<h3>Documents</h3>{detail.documents.length ? detail.documents.map((item: Row) => <div className="owner-document" key={item.id}><span>{item.filename} · version {item.version}</span><Button size="sm" variant="outline" onClick={() => open({ user: detail.account, action: 'download', document: item })}><ArrowDownToLine size={14} />Download</Button></div>) : <p>No documents stored.</p>}<h3>Discovery sources</h3><ul>{detail.sources.map((source: Row) => <li key={source.id}>{source.company} · {source.kind} · {source.status}</li>)}</ul></div></section>}
    <section className="panel mt-6"><div className="panel-head"><div><h2>Owner access log</h2><p>Most recent 200 owner events across this installation.</p></div></div><div className="owner-audit">{audit.map(row => <div key={row.id}><strong>{row.kind.replaceAll('_', ' ')}</strong><p>{row.message}</p><small>{date(row.created_at)}</small></div>)}{!audit.length && <p>No owner actions recorded yet.</p>}</div></section>
    <Dialog.Root open={!!review} onOpenChange={value => { if (!value && !busy) close(); }}><Dialog.Portal><Dialog.Overlay className="modal-overlay" /><Dialog.Content className="modal"><div className="modal-head"><div><Dialog.Title>{review ? labels[review.action] : 'Owner action'}</Dialog.Title><Dialog.Description>Confirm access to {review?.user.email}. This action is audited.</Dialog.Description></div><button className="icon-btn" disabled={busy} aria-label="Close owner action" onClick={close}><X size={19} /></button></div><form className="modal-body" onSubmit={submit}>
      <label className="field"><span className="field-label">Access reason</span><input aria-label="Access reason" required minLength={8} maxLength={300} value={purpose} onChange={event => setPurpose(event.target.value)} placeholder="For example: requested account support" /><span className="field-hint">This reason is recorded. Do not include passwords or private answers.</span></label>
      <label className="field"><span className="field-label">Your owner password</span><input required type="password" autoComplete="current-password" value={password} onChange={event => setPassword(event.target.value)} /></label>
      {review?.action === 'password' && <><label className="field"><span className="field-label">Replacement password</span><input required type="password" minLength={12} maxLength={256} autoComplete="new-password" value={replacement} onChange={event => setReplacement(event.target.value)} /></label><label className="field"><span className="field-label">Confirm replacement password</span><input required type="password" autoComplete="new-password" value={confirmation} onChange={event => setConfirmation(event.target.value)} /></label><p className="muted">The original password cannot be retrieved. This resets it, revokes sessions and pauses the account’s automation. Share the replacement privately.</p></>}
      {review?.action === 'status' && <p className="muted">{review.user.disabled ? 'Enabling sign-in does not resume automation. The account holder must review their policy.' : 'Disabling this account revokes its sessions and pauses automation.'}</p>}
      <label className="check-label mt-4"><input type="checkbox" required checked={consent} onChange={event => setConsent(event.target.checked)} />I approve this specific owner action.</label>{actionError && <p role="alert" className="owner-action-error">{actionError}</p>}<div className="detail-actions mt-4"><Button type="submit" disabled={busy || !consent}>{busy && <LoaderCircle size={15} className="spin" />}Confirm owner action</Button><Button type="button" variant="outline" disabled={busy} onClick={close}>Cancel</Button></div>
    </form></Dialog.Content></Dialog.Portal></Dialog.Root>
  </>;
}

'use client';
import { useEffect, useState, type FormEvent } from 'react';
import { Button } from '@/components/ui/button';
import { OwnerMembers } from './owner-members';
import { MFASettings } from './mfa-settings';
type Api = <T = unknown>(path: string, method?: string, body?: unknown) => Promise<T>;
type Props = {
  api: Api;
  download: (path: string, body: unknown) => Promise<Blob>;
  notify: (message: string, error?: boolean) => void;
};
type Report = { [key: string]: unknown };
const tabs = [
  'Overview',
  'Members',
  'Activity',
  'Analytics',
  'Security',
  'Applications',
  'Automation',
  'Infrastructure',
  'Settings',
] as const;
export function OwnerConsole({ api, download, notify }: Props) {
  const [tab, setTab] = useState<(typeof tabs)[number]>('Overview');
  const [unlocked, setUnlocked] = useState(false);
  const [password, setPassword] = useState('');
  const [otp, setOtp] = useState('');
  const [consent, setConsent] = useState(false);
  const [data, setData] = useState<Report | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    if (!unlocked || tab === 'Members') return;
    let active = true;
    setBusy(true);
    setData(null);
    setError('');
    api<Report>(`/owner/report?section=${tab.toLowerCase()}`)
      .then((r) => {
        if (active) setData(r);
      })
      .catch((e) => {
        if (active) {
          setError(e.message);
          if (e.status === 403) setUnlocked(false);
        }
      })
      .finally(() => {
        if (active) setBusy(false);
      });
    return () => {
      active = false;
    };
  }, [api, tab, unlocked, revision]);
  async function unlock(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      await api('/owner/unlock', 'POST', {
        current_password: password,
        otp,
        consent,
        purpose: 'Review private founder administration',
      });
      setUnlocked(true);
      setPassword('');
      setOtp('');
      setConsent(false);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const rows = (key: string) => (Array.isArray(data?.[key]) ? (data[key] as Record<string, unknown>[]) : []);
  return (
    <div className="founder-console">
      <div className="page-title-row">
        <div>
          <div className="section-kicker">FOUNDER ONLY</div>
          <h1>Owner’s desk</h1>
          <p className="page-subtitle">Your members, security and operations. Sensitive access is audited.</p>
        </div>
        {unlocked && (
          <Button variant="outline" disabled={busy} onClick={() => setRevision((v) => v + 1)}>
            Refresh report
          </Button>
        )}
      </div>
      <nav className="founder-tabs" aria-label="Founder sections">
        {tabs.map((item) => (
          <button
            type="button"
            key={item}
            aria-current={tab === item ? 'page' : undefined}
            onClick={() => setTab(item)}
          >
            {item}
          </button>
        ))}
      </nav>
      {error && <p role="alert">{error}</p>}
      {!unlocked ? (
        <section className="panel founder-unlock">
          <h2>Confirm it’s you.</h2>
          <p>
            Unlock private reports for five minutes. Account changes still require a fresh password check.
          </p>
          <form onSubmit={unlock} className="founder-form">
            <label className="field">
              <span className="field-label">Founder password</span>
              <input
                required
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </label>
            <label className="field">
              <span className="field-label">Authenticator code, if required</span>
              <input
                inputMode="numeric"
                autoComplete="one-time-code"
                pattern="[0-9]{6}"
                maxLength={6}
                value={otp}
                onChange={(e) => setOtp(e.target.value)}
              />
            </label>
            <label className="check-label">
              <input
                required
                type="checkbox"
                checked={consent}
                onChange={(e) => setConsent(e.target.checked)}
              />
              I authorize this audited administration session.
            </label>
            <Button disabled={busy} type="submit">
              {busy ? 'Checking…' : 'Unlock founder console'}
            </Button>
          </form>
        </section>
      ) : tab === 'Members' ? (
        <OwnerMembers api={api} download={download} notify={notify} />
      ) : (
        <>
          <div aria-live="polite">{busy ? 'Loading private report…' : null}</div>
          {data && (
            <>
              <dl className="founder-facts">
                {Object.entries(data)
                  .filter(([, v]) => ['string', 'number', 'boolean'].includes(typeof v))
                  .map(([key, value]) => (
                    <div key={key}>
                      <dt>{key.replaceAll('_', ' ')}</dt>
                      <dd>{typeof value === 'boolean' ? (value ? 'Yes' : 'No') : String(value)}</dd>
                    </div>
                  ))}
              </dl>
              {['application_statuses', 'queue', 'sources'].map((key) =>
                data[key] && typeof data[key] === 'object' && Object.keys(data[key] as object).length ? (
                  <section key={key} className="founder-section">
                    <h2>{key.replaceAll('_', ' ')}</h2>
                    <dl className="founder-facts">
                      {Object.entries(data[key] as Record<string, number>).map(([state, count]) => (
                        <div key={state}>
                          <dt>{state}</dt>
                          <dd>{count}</dd>
                        </div>
                      ))}
                    </dl>
                  </section>
                ) : null,
              )}
              {['registrations_by_day', 'events', 'audit', 'applications', 'workers'].map((key) =>
                rows(key).length ? (
                  <section className="founder-section" key={key}>
                    <h2>{key.replaceAll('_', ' ')}</h2>
                    <div className="table-scroll">
                      <table className="owner-users">
                        <thead>
                          <tr>
                            {Object.keys(rows(key)[0]).map((col) => (
                              <th key={col}>{col.replaceAll('_', ' ')}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {rows(key).map((row, index) => (
                            <tr key={String(row.id || index)}>
                              {Object.entries(row).map(([col, value]) => (
                                <td key={col}>{value == null ? 'Unknown' : String(value)}</td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </section>
                ) : null,
              )}
              {!busy &&
                ['Activity', 'Applications'].includes(tab) &&
                !rows(tab === 'Activity' ? 'events' : 'applications').length && <p>No records yet.</p>}
            </>
          )}
          {tab === 'Security' && <MFASettings api={api} />}
          {tab === 'Settings' && (
            <p>
              Provision or transfer the sole founder through the trusted local CLI. Deployment secrets are
              never displayed here.
            </p>
          )}
        </>
      )}
    </div>
  );
}

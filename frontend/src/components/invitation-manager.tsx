'use client';
import { useEffect, useState, type FormEvent } from 'react';
import { Button } from '@/components/ui/button';
type Invite = { id: string; email: string; status: string; expires_at: string };
type Api = <T = unknown>(path: string, method?: string, body?: unknown) => Promise<T>;
export function InvitationManager({
  api,
  notify,
}: {
  api: Api;
  notify: (message: string, error?: boolean) => void;
}) {
  const [items, setItems] = useState<Invite[]>([]);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [otp, setOtp] = useState('');
  const [consent, setConsent] = useState(false);
  const [pending, setPending] = useState(false);
  const [revoking, setRevoking] = useState<Invite | null>(null);
  const [link, setLink] = useState('');
  const [error, setError] = useState('');
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let active = true;
    api<{ items: Invite[] }>('/owner/invitations')
      .then((result) => {
        if (active) setItems(result.items);
      })
      .catch((reason: Error) => {
        if (active) setError(reason.message);
      });
    return () => {
      active = false;
    };
  }, [api, revision]);
  async function submit(event: FormEvent) {
    event.preventDefault();
    setPending(true);
    setError('');
    setLink('');
    const body = {
      current_password: password,
      otp,
      consent,
      purpose: revoking
        ? 'Revoke an unused workspace invitation'
        : 'Authorize this email to join the private workspace',
    };
    try {
      if (revoking) await api(`/owner/invitations/${revoking.id}/revoke`, 'POST', body);
      else {
        const created = await api<{ token: string }>('/owner/invitations', 'POST', {
          ...body,
          email,
          expires_days: 7,
        });
        setLink(`${window.location.origin}/register#invitation=${encodeURIComponent(created.token)}`);
      }
      setPassword('');
      setOtp('');
      setConsent(false);
      setEmail('');
      setRevoking(null);
      setRevision((value) => value + 1);
      notify(revoking ? 'Invitation revoked.' : 'Invitation created. Share the one-time link privately.');
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setPending(false);
    }
  }
  return (
    <section className="panel mt-6 invitation-manager" aria-labelledby="invitation-title">
      <div className="panel-head">
        <div>
          <h2 id="invitation-title">Workspace invitations</h2>
          <p>One email. One use. Seven days. No invitation emails are sent automatically.</p>
        </div>
      </div>
      <form onSubmit={submit} className="invitation-form">
        <label className="field">
          <span className="field-label">Authenticator code for invitation</span>
          <input
            inputMode="numeric"
            autoComplete="one-time-code"
            pattern="[0-9]{6}"
            maxLength={6}
            value={otp}
            onChange={(event) => setOtp(event.target.value)}
          />
        </label>
        {revoking ? (
          <p>
            Revoke access for the unused invitation to <strong>{revoking.email}</strong>.
          </p>
        ) : (
          <label className="field">
            <span className="field-label">Invited email address</span>
            <input
              type="email"
              required
              maxLength={254}
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              autoComplete="off"
            />
          </label>
        )}
        <label className="field">
          <span className="field-label">Confirm your owner password</span>
          <input
            type="password"
            autoComplete="current-password"
            required
            maxLength={256}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </label>
        <label className="check-label">
          <input
            type="checkbox"
            required
            checked={consent}
            onChange={(event) => setConsent(event.target.checked)}
          />
          {revoking ? 'I authorize revoking this invitation.' : 'I authorize this email address to join.'}
        </label>
        {error && (
          <p role="alert" className="error-text">
            {error}
          </p>
        )}
        <div className="actions">
          <Button type="submit" disabled={pending}>
            {pending ? 'Working…' : revoking ? 'Confirm revocation' : 'Create invitation'}
          </Button>
          {revoking && (
            <Button
              type="button"
              variant="outline"
              disabled={pending}
              onClick={() => {
                setRevoking(null);
                setPassword('');
                setConsent(false);
              }}
            >
              Cancel
            </Button>
          )}
        </div>
      </form>
      {link && (
        <div className="invitation-result" role="status">
          <label className="field">
            <span className="field-label">One-time invitation link</span>
            <input readOnly value={link} onFocus={(event) => event.target.select()} />
          </label>
          <p>Copy this link now. It is shown only once and works only for the invited email.</p>
          <Button variant="outline" onClick={() => setLink('')}>
            Dismiss link
          </Button>
        </div>
      )}
      <ul className="invitation-list">
        {items.map((item) => (
          <li key={item.id}>
            <span>
              <strong>{item.email}</strong>
              <small>
                {item.status} · Expires {new Date(item.expires_at).toLocaleDateString()}
              </small>
            </span>
            {item.status === 'pending' && (
              <Button
                size="sm"
                variant="outline"
                onClick={() => {
                  setRevoking(item);
                  setPassword('');
                  setConsent(false);
                  setLink('');
                }}
              >
                Revoke invitation
              </Button>
            )}
          </li>
        ))}
      </ul>
      {!items.length && (
        <p className="muted">No invitations issued yet. Existing accounts are managed below.</p>
      )}
      <p className="muted">
        Shows up to 100 invitations you issued, pending first. Disabling an existing account revokes its
        sessions.
      </p>
    </section>
  );
}

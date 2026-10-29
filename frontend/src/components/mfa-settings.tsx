'use client';
import { useEffect, useState, type FormEvent } from 'react';
import { Button } from '@/components/ui/button';
type Api = <T = unknown>(path: string, method?: string, body?: unknown) => Promise<T>;
export function MFASettings({ api }: { api: Api }) {
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [password, setPassword] = useState('');
  const [otp, setOtp] = useState('');
  const [secret, setSecret] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let active = true;
    api<{ enabled: boolean }>('/auth/mfa')
      .then((r) => {
        if (active) setEnabled(r.enabled);
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [api]);
  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      const action = enabled ? 'disable' : secret ? 'enable' : 'setup';
      const result = await api<{ secret?: string; enabled?: boolean }>(`/auth/mfa/${action}`, 'POST', {
        current_password: password,
        otp,
      });
      if (result.secret) setSecret(result.secret);
      else {
        setEnabled(!!result.enabled);
        setSecret('');
      }
      setPassword('');
      setOtp('');
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="panel form-section">
      <div className="form-section-intro">
        <h2>Authenticator protection</h2>
        <p>
          {enabled === null
            ? 'Checking MFA…'
            : enabled
              ? 'MFA is enabled. Sign-ins require an authenticator code.'
              : 'Add an authenticator app as a second factor.'}
        </p>
        <p>
          Lost founder authenticator? Use the trusted local recovery CLI. Password resets do not remove MFA.
        </p>
      </div>
      <form onSubmit={submit} className="founder-form">
        {secret && (
          <div role="status">
            <p>
              Add this setup key manually to your authenticator as “InternPilot”. It is shown only during this
              setup; never share it.
            </p>
            <label className="field">
              <span className="field-label">Authenticator setup key</span>
              <input readOnly value={secret} autoComplete="off" onFocus={(event) => event.target.select()} />
            </label>
          </div>
        )}
        <label className="field">
          <span className="field-label">Confirm current password for MFA</span>
          <input
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>
        {(enabled || secret) && (
          <label className="field">
            <span className="field-label">Fresh authenticator code</span>
            <input
              required
              inputMode="numeric"
              autoComplete="one-time-code"
              pattern="[0-9]{6}"
              maxLength={6}
              value={otp}
              onChange={(e) => setOtp(e.target.value)}
            />
          </label>
        )}
        {error && <p role="alert">{error}</p>}
        <Button disabled={busy || enabled === null} type="submit">
          {busy ? 'Working…' : enabled ? 'Disable MFA' : secret ? 'Confirm and enable MFA' : 'Set up MFA'}
        </Button>
      </form>
    </section>
  );
}

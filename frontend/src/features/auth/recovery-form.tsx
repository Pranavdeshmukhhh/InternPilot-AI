'use client';
import { useEffect, useState, type FormEvent } from 'react';
import Link from 'next/link';
import { PublicShell } from '@/features/public/shell';
import { api } from '@/lib/api-client';
import { Button } from '@/components/ui/button';
export function RecoveryForm() {
  const [token, setToken] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [done, setDone] = useState(false);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    const value = new URLSearchParams(window.location.hash.slice(1)).get('recovery');
    if (value) {
      setToken(value);
      window.history.replaceState(window.history.state, '', window.location.pathname);
    }
  }, []);
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (password !== confirm) {
      setError('Passwords do not match.');
      return;
    }
    setBusy(true);
    setError('');
    try {
      await api('/auth/recover', 'POST', { token, new_password: password });
      setDone(true);
      setToken('');
      setPassword('');
      setConfirm('');
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <PublicShell>
      <main id="public-main" className="public-prose">
        <h1>{done ? 'A fresh start.' : 'Reset your password.'}</h1>
        {done ? (
          <>
            <p>
              Your password is updated. Old sessions are signed out. MFA is unchanged and automation remains
              paused.
            </p>
            <Link href="/login">Sign in →</Link>
          </>
        ) : (
          <>
            <p>
              Use the private, one-time recovery link supplied by the founder. Links expire after 30 minutes.
            </p>
            <form onSubmit={submit} className="founder-form">
              <label className="field">
                <span className="field-label">Recovery code</span>
                <input
                  required
                  type="password"
                  autoComplete="off"
                  value={token}
                  onChange={(e) => setToken(e.target.value)}
                />
              </label>
              <label className="field">
                <span className="field-label">New password</span>
                <input
                  required
                  type="password"
                  minLength={12}
                  maxLength={256}
                  autoComplete="new-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
              </label>
              <label className="field">
                <span className="field-label">Confirm new password</span>
                <input
                  required
                  type="password"
                  autoComplete="new-password"
                  value={confirm}
                  onChange={(e) => setConfirm(e.target.value)}
                />
              </label>
              {error && <p role="alert">{error}</p>}
              <Button disabled={busy} type="submit">
                {busy ? 'Updating…' : 'Set new password'}
              </Button>
            </form>
          </>
        )}
      </main>
    </PublicShell>
  );
}

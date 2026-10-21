'use client';

import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { Check, LoaderCircle, LockKeyhole, LogOut, RefreshCw, ShieldCheck } from 'lucide-react';
import { Button } from '@/components/ui/button';

type Item = Record<string, any>;
type Props = {
  api: (path: string, method?: string, body?: unknown) => Promise<any>;
  onSession: (session: Item) => void;
  notify: (message: string, error?: boolean) => void;
};

export function AccountSecurityView({ api, onSession, notify }: Props) {
  const [activeSessions, setActiveSessions] = useState<number | null>(null);
  const [sessionsLoading, setSessionsLoading] = useState(true);
  const [sessionsError, setSessionsError] = useState('');
  const [busy, setBusy] = useState<'password' | 'sessions' | null>(null);
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [passwordError, setPasswordError] = useState('');

  const refreshSessions = useCallback(async () => {
    setSessionsLoading(true);
    setSessionsError('');
    try {
      const result = await api('/auth/sessions');
      setActiveSessions(result.active_sessions);
    } catch (error) {
      setActiveSessions(null);
      setSessionsError((error as Error).message);
    } finally {
      setSessionsLoading(false);
    }
  }, [api]);

  useEffect(() => { void refreshSessions(); }, [refreshSessions]);

  const updatePassword = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (newPassword !== confirmation) {
      setPasswordError('Your new passwords do not match.');
      return;
    }
    setPasswordError('');
    setBusy('password');
    try {
      const session = await api('/auth/password', 'POST', { current_password: currentPassword, new_password: newPassword });
      onSession(session);
      setCurrentPassword('');
      setNewPassword('');
      setConfirmation('');
      notify('Password updated. Your current session has been renewed.');
      await refreshSessions();
    } catch (error) {
      notify((error as Error).message, true);
    } finally {
      setBusy(null);
    }
  };

  const revokeOtherSessions = async () => {
    setBusy('sessions');
    try {
      const result = await api('/auth/logout-others', 'POST', {});
      const count = result.revoked_sessions;
      notify(count === 0 ? 'No other active sessions to sign out.' : `${count} other ${count === 1 ? 'session signed' : 'sessions signed'} out.`);
      await refreshSessions();
    } catch (error) {
      notify((error as Error).message, true);
    } finally {
      setBusy(null);
    }
  };

  return <>
    <div className="page-title-row"><div><div className="section-kicker">YOUR PRIVATE WORKSPACE</div><h1>Account security.</h1><p className="page-subtitle">Manage your password and the sessions that can access your account.</p></div></div>
    <section className="panel form-section">
      <div className="form-section-intro"><span className="form-section-icon"><ShieldCheck size={20} /></span><h2>Active sessions</h2><p>Review account access and sign out your other browsers or devices.</p></div>
      <div>
        <div className="detail-summary"><div><strong>{sessionsLoading ? 'Checking active sessions…' : activeSessions === null ? 'Session count unavailable' : `${activeSessions} active ${activeSessions === 1 ? 'session' : 'sessions'}`}</strong></div><Button variant="ghost" size="sm" disabled={!!busy || sessionsLoading} onClick={refreshSessions} aria-label="Refresh active sessions"><RefreshCw size={15} className={sessionsLoading ? 'spin' : ''} />Refresh</Button></div>
        {sessionsError && <p className="muted" role="alert">{sessionsError}</p>}
        <p className="muted">This includes your current session. Signing out other sessions keeps this workspace open.</p>
        <div className="detail-actions"><Button variant="outline" disabled={!!busy || sessionsLoading || activeSessions === null || activeSessions <= 1} onClick={revokeOtherSessions}>{busy === 'sessions' ? <LoaderCircle size={16} className="spin" /> : <LogOut size={16} />}Sign out other sessions</Button></div>
      </div>
    </section>
    <form onSubmit={updatePassword}>
      <section className="panel form-section">
        <div className="form-section-intro"><span className="form-section-icon"><LockKeyhole size={20} /></span><h2>Change password</h2><p>Use at least 12 characters and choose a password unique to this account.</p></div>
        <div className="form-grid">
          <label className="field"><span className="field-label">Current password</span><input type="password" autoComplete="current-password" required value={currentPassword} disabled={!!busy} onChange={event => setCurrentPassword(event.target.value)} /></label>
          <label className="field"><span className="field-label">New password</span><input type="password" autoComplete="new-password" minLength={12} required value={newPassword} disabled={!!busy} onChange={event => { setNewPassword(event.target.value); setPasswordError(''); }} /></label>
          <label className="field"><span className="field-label">Confirm new password</span><input type="password" autoComplete="new-password" minLength={12} required value={confirmation} disabled={!!busy} aria-invalid={!!passwordError} aria-describedby={passwordError ? 'password-confirmation-error' : undefined} onChange={event => { setConfirmation(event.target.value); setPasswordError(''); }} />{passwordError && <span id="password-confirmation-error" className="field-hint" role="alert">{passwordError}</span>}</label>
        </div>
      </section>
      <div className="save-bar"><span><LockKeyhole size={14} />Your current session is renewed after a password change.</span><Button type="submit" disabled={!!busy}>{busy === 'password' ? <LoaderCircle size={16} className="spin" /> : <Check size={16} />}Update password</Button></div>
    </form>
  </>;
}

'use client';
import { BrandMark } from '@/features/public/brand';
import { usePathname } from 'next/navigation';
import { useState, useEffect, type FormEvent } from 'react';

import { ArrowRight, LoaderCircle, LockKeyhole, ShieldCheck } from 'lucide-react';
import { Button } from '@/components/ui/button';

import { ThemeToggle } from '@/components/theme-toggle';

import { api } from '@/lib/api-client';
import type { Session, Health } from '@/lib/api-types';

import { Field } from '@/features/shared/primitives';
export function Auth({
  onLogin,
  notify,
}: {
  onLogin: (d: Session) => void;
  notify: (msg: string, error?: boolean) => void;
}) {
  const pathname = usePathname();
  const [register, setRegister] = useState(pathname !== '/login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [otp, setOtp] = useState('');
  const [invite, setInvite] = useState('');
  const [authSettings, setAuthSettings] = useState<Health | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    const readInvitation = () => {
      const invitation = new URLSearchParams(window.location.hash.slice(1)).get('invitation');
      if (pathname === '/register' && invitation) {
        setInvite(invitation);
        // Keep the bearer secret out of browser history and later copied URLs.
        window.history.replaceState(
          window.history.state,
          '',
          window.location.pathname + window.location.search,
        );
      }
    };
    readInvitation();
    window.addEventListener('hashchange', readInvitation);
    return () => window.removeEventListener('hashchange', readInvitation);
  }, [pathname]);
  useEffect(() => {
    api<Health>('/health')
      .then((d) => {
        setAuthSettings(d);
        if (!d.allow_registration) setRegister(false);
      })
      .catch((e) => notify(e.message, true));
  }, [notify]);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      onLogin(
        await api<Session>(`/auth/${register ? 'register' : 'login'}`, 'POST', {
          email,
          password,
          ...(!register ? { otp } : {}),
          ...(register ? { registration_token: invite } : {}),
        }),
      );
    } catch (e) {
      notify((e as Error).message, true);
    } finally {
      setBusy(false);
    }
  };
  return (
    <main className="auth-page">
      <div className="auth-story">
        <div className="brand">
          <span className="brand-symbol brand-mark-shell">
            <BrandMark size={28} />
          </span>
          <span>InternPilot</span>
        </div>
        <div className="auth-story-body">
          <span className="auth-kicker">
            <span className="pulse-dot" /> YOUR NEXT BEGINNING
          </span>
          <h1>
            Find your next
            <br />
            internship.
            <br />
            <em>Keep the search simple.</em>
          </h1>
          <p>
            Find internships and hackathons, save the promising ones, and keep track of every application.
          </p>
          <div className="auth-proof">
            <ShieldCheck size={22} />
            <span>
              Application uploads need your approval.
              <br />
              <strong>You decide when an application is submitted.</strong>
            </span>
          </div>
        </div>
        <span className="auth-foot">Internships, hackathons, and a place to keep it all.</span>
        <div className="orb orb-one" />
        <div className="orb orb-two" />
      </div>
      <div className="auth-form-side">
        <div className="auth-form">
          <div className="auth-theme">
            <ThemeToggle />
          </div>
          <div className="section-kicker">YOUR OPPORTUNITY WORKSPACE</div>
          <h2>
            {register
              ? authSettings?.registration_requires_invite
                ? 'Activate your invitation.'
                : 'Start your notebook.'
              : 'Welcome back.'}
          </h2>
          <p className="muted">
            {register
              ? authSettings?.registration_requires_invite
                ? 'Use the email your owner approved and choose your own password.'
                : 'Create your private account to start discovering opportunities.'
              : 'Sign in to your private workspace. New accounts require an owner invitation.'}
          </p>
          <form onSubmit={submit}>
            <Field label="Email address">
              <input
                type="email"
                required
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
              />
            </Field>
            <Field
              label="Password"
              hint={
                register ? 'Use at least 12 characters. This protects your private workspace.' : undefined
              }
            >
              <input
                type="password"
                required
                minLength={register ? 12 : undefined}
                autoComplete={register ? 'new-password' : 'current-password'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder={register ? 'Create a strong password' : 'Enter your password'}
              />
            </Field>
            {register && authSettings?.registration_requires_invite && (
              <Field
                label="Invitation code"
                hint="Use the private code supplied by your workspace administrator."
              >
                <input
                  type="password"
                  required
                  autoComplete="off"
                  value={invite}
                  onChange={(e) => setInvite(e.target.value)}
                />
              </Field>
            )}
            {!register && (
              <Field label="Authenticator code" hint="If MFA is enabled, enter a fresh six-digit code.">
                <input
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  maxLength={6}
                  pattern="[0-9]{6}"
                  value={otp}
                  onChange={(event) => setOtp(event.target.value)}
                />
              </Field>
            )}
            <Button type="submit" className="w-full" disabled={busy || !authSettings}>
              {busy ? <LoaderCircle className="spin" size={17} /> : null}
              {register
                ? authSettings?.registration_requires_invite
                  ? 'Activate account'
                  : 'Create your workspace'
                : 'Sign in'}
              <ArrowRight size={17} />
            </Button>
          </form>
          <p className="auth-owner-disclosure">
            The workspace owner can access account records for administration. Passwords remain unreadable and
            private-record access is logged.
          </p>
          <div className="auth-switch">
            {register ? 'Already have an account?' : 'Have an invitation?'}{' '}
            <button
              disabled={!register && !authSettings?.allow_registration}
              onClick={() => setRegister(!register)}
            >
              {register ? 'Sign in' : 'Activate invitation'}
            </button>
          </div>
          <div className="privacy-note">
            <LockKeyhole size={15} /> Encrypted profile & documents · Discovery mode by default
          </div>
        </div>
      </div>
    </main>
  );
}

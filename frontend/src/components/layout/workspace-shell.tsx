'use client';
import { BrandMark } from '@/features/public/brand';

import { useEffect, useState, type ReactNode } from 'react';
import Link from 'next/link';
import * as Dialog from '@radix-ui/react-dialog';
import {
  ArrowUpRight,
  Bell,
  Bookmark,
  BriefcaseBusiness,
  Command,
  Compass,
  FileText,
  LayoutDashboard,
  LockKeyhole,
  LogOut,
  Mail,
  Menu,
  Settings2,
  X,
  Activity,
  Shield,
} from 'lucide-react';
import { ThemeToggle } from '@/components/theme-toggle';
import { routes, type View } from '@/lib/routes';
import type { Session } from '@/lib/api-types';

const navigation = [
  ['overview', 'Overview', LayoutDashboard],
  ['discover', 'Explore', Compass],
  ['saved', 'Saved', Bookmark],
  ['applications', 'Applications', BriefcaseBusiness],
  ['documents', 'Documents', FileText],
  ['outreach', 'Outreach', Mail],
  ['automation', 'Automation', Activity],
] as const;
const labels: Record<View, string> = {
  overview: 'Overview',
  discover: 'Internships',
  hackathons: 'Hackathons',
  recommended: 'Your matches',
  saved: 'Saved',
  applications: 'Applications',
  documents: 'Documents',
  outreach: 'Outreach',
  automation: 'Automation',
  sources: 'Discovery sources',
  controls: 'Application policies',
  activity: 'Activity & logs',
  notifications: 'Notifications',
  profile: 'Your profile',
  security: 'Account security',
  owner: 'Owner console',
};

export function WorkspaceShell({
  view,
  session,
  name,
  stopped,
  unread,
  onCommand,
  onSignOut,
  children,
}: {
  view: View;
  session: Session;
  name?: string;
  stopped: boolean;
  unread: number;
  onCommand: () => void;
  onSignOut: () => void;
  children: ReactNode;
}) {
  const [mobile, setMobile] = useState(false);
  useEffect(() => setMobile(false), [view]);
  const active = (id: View) =>
    id === view ||
    (id === 'discover' && ['hackathons', 'recommended'].includes(view)) ||
    (id === 'automation' && ['sources', 'controls', 'activity'].includes(view));
  const navigationBody = (
    <>
      <Link href="/overview" prefetch={false} className="brand" aria-label="InternPilot overview">
        <span className="brand-symbol brand-mark-shell">
          <BrandMark size={28} />
        </span>
        <span>
          InternPilot<span className="brand-caption">A little more possibility.</span>
        </span>
      </Link>
      <button
        className="workspace-search"
        onClick={() => {
          setMobile(false);
          onCommand();
        }}
      >
        <Compass size={16} aria-hidden="true" />
        <span>Find anything</span>
        <kbd>⌘ K</kbd>
      </button>
      <nav aria-label="Main navigation">
        {navigation.map(([id, label, Icon]) => (
          <Link
            key={id}
            href={routes[id]}
            prefetch={false}
            aria-current={active(id) ? 'page' : undefined}
            className={`nav-item ${active(id) ? 'active' : ''}`}
          >
            <Icon size={18} strokeWidth={1.7} aria-hidden="true" />
            {label}
          </Link>
        ))}
      </nav>
      <div className="rail-footer">
        <div className="rail-note">
          <span className={`status-dot ${stopped ? 'warning' : ''}`} />
          {stopped ? 'Activity paused' : 'Your workspace, your pace'}
        </div>
        <Link href={routes.profile} prefetch={false} className="account">
          <span className="avatar" aria-hidden="true">
            {(name || session.user.email).slice(0, 1).toUpperCase()}
          </span>
          <span>
            <strong>{name || 'Your profile'}</strong>
            <small>Personal workspace</small>
          </span>
          <Settings2 size={16} />
        </Link>
        <div className="rail-utilities">
          <Link href={routes.security} prefetch={false}>
            <LockKeyhole size={14} />
            Account
          </Link>
          {session.user.role === 'owner' && (
            <Link href={routes.owner} prefetch={false}>
              <Shield size={14} />
              Owner
            </Link>
          )}
          <button onClick={onSignOut} aria-label="Sign out">
            <LogOut size={15} />
          </button>
        </div>
      </div>
    </>
  );
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      <aside className="sidebar">{navigationBody}</aside>
      <Dialog.Root open={mobile} onOpenChange={setMobile}>
        <Dialog.Portal>
          <Dialog.Overlay className="nav-backdrop" />
          <Dialog.Content className="mobile-navigation">
            <Dialog.Title className="sr-only">Workspace navigation</Dialog.Title>
            <Dialog.Description className="sr-only">Choose a workspace destination.</Dialog.Description>
            <Dialog.Close className="mobile-nav-close icon-btn" aria-label="Close navigation">
              <X size={20} />
            </Dialog.Close>
            {navigationBody}
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumb">
            <button
              className="icon-btn mobile-menu"
              aria-label="Open navigation"
              onClick={() => setMobile(true)}
            >
              <Menu size={20} />
            </button>
            <span className="workspace-crumb">Personal workspace</span>
            <span className="crumb-divider">/</span>
            <strong>{labels[view]}</strong>
          </div>
          <div className="topbar-actions">
            <button
              className="icon-btn command-trigger"
              onClick={onCommand}
              aria-label="Open command menu"
              aria-keyshortcuts="Control+k Meta+k"
            >
              <Command size={17} />
            </button>
            <ThemeToggle />
            <Link
              href={routes.notifications}
              prefetch={false}
              className="icon-btn notification-trigger"
              aria-label={`Notifications${unread ? ` (${unread} unread)` : ''}`}
            >
              <Bell size={18} />
              {unread > 0 && <span className="notification-dot" />}
            </Link>
          </div>
        </header>
        <main id="main-content" className="main-content" tabIndex={-1}>
          {children}
        </main>
        <footer className="workspace-footer">
          <span>
            <LockKeyhole size={12} />
            Private records. Explicit approvals.
          </span>
          <Link prefetch={false} href={routes.controls}>
            Your automation boundaries
            <ArrowUpRight size={12} />
          </Link>
        </footer>
      </div>
    </div>
  );
}

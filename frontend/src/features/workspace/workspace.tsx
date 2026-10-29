'use client';

import dynamic from 'next/dynamic';
import { useQueryClient } from '@tanstack/react-query';
import { resourceKey } from '@/lib/query-keys';
import type { WorkerStatus } from '@/lib/api-types';
import { sessionEpoch } from '@/lib/api-client';
import Link from 'next/link';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { useCallback, useEffect, useRef, useState } from 'react';
import { LoaderCircle, Pause, RefreshCw, Waves, X, XCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { WorkspaceShell } from '@/components/layout/workspace-shell';
import { useBrowserNotifications } from '@/features/notifications/use-browser-notifications';
import { Auth } from '@/features/auth/auth-view';
import { Modal, PageTitle, EventList, WorkerSummary } from '@/features/shared/primitives';
import { Overview } from '@/features/overview/overview-view';
import { api } from '@/lib/api-client';
import { routes, viewForPath } from '@/lib/routes';
import type {
  Application,
  AuditEvent,
  Dashboard,
  Document,
  Health,
  Notification,
  Opportunity,
  OpportunityPage,
  Policy,
  Profile,
  Source,
  Task,
} from '@/lib/api-types';
import type { LegacyItem, Perform } from '@/lib/legacy-types';
import { useInvalidation, useResource, useSession, useWorkspaceEvents } from './provider';

const lazy = () => <Skeleton />;
const Explorer = dynamic(
  () => import('@/components/opportunity-explorer').then((m) => m.OpportunityExplorer),
  { loading: lazy },
);
const Applications = dynamic(
  () => import('@/features/applications/applications-view').then((m) => m.ApplicationsView),
  { loading: lazy },
);
const Documents = dynamic(() => import('@/features/documents/documents-view').then((m) => m.DocumentsView), {
  loading: lazy,
});
const ProfileView = dynamic(() => import('@/features/account/profile-view').then((m) => m.ProfileView), {
  loading: lazy,
});
const PolicyView = dynamic(() => import('@/features/automation/policy-view').then((m) => m.PolicyView), {
  loading: lazy,
});
const Sources = dynamic(() => import('@/features/automation/sources-view').then((m) => m.SourcesView), {
  loading: lazy,
});
const Notifications = dynamic(
  () => import('@/features/notifications/notifications-view').then((m) => m.NotificationsView),
  { loading: lazy },
);
const JobDetail = dynamic(
  () => import('@/features/opportunities/opportunity-detail').then((m) => m.JobDetail),
  { loading: lazy },
);
const Security = dynamic(
  () => import('@/components/account-security-view').then((m) => m.AccountSecurityView),
  { loading: lazy },
);
const Owner = dynamic(() => import('@/components/owner-console').then((m) => m.OwnerConsole), {
  loading: lazy,
});
const Outreach = dynamic(() => import('@/components/outreach-view').then((m) => m.OutreachView), {
  loading: lazy,
});
const Automation = dynamic(() => import('@/components/automation-center').then((m) => m.AutomationCenter), {
  loading: lazy,
});
const CommandMenu = dynamic(() => import('@/features/workspace/command-menu').then((m) => m.CommandMenu));

export function Workspace() {
  const { session, checking, login, clear } = useSession();
  const queryClient = useQueryClient();
  const updateNotificationSettings = useCallback(
    (value: LegacyItem) => {
      if (session)
        queryClient.setQueryData(
          resourceKey(session.user.id, sessionEpoch(), '/notification-settings'),
          value,
        );
    },
    [queryClient, session],
  );
  const pathname = usePathname();
  const router = useRouter();
  const search = useSearchParams();
  const view = viewForPath(pathname) || 'overview';
  const authenticated = !!session;
  const [busy, setBusy] = useState('');
  const [command, setCommand] = useState(false);
  const [toast, setToast] = useState<{ text: string; error: boolean } | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const notify = useCallback((text: string, error = false) => {
    setToast({ text, error });
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => setToast(null), 8000);
  }, []);
  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current);
    },
    [],
  );
  const invalidate = useInvalidation();
  useWorkspaceEvents();
  const profile = useResource<Profile>('/profile');
  const policy = useResource<Policy>('/policy');
  const dashboard = useResource<Dashboard>('/dashboard', view === 'overview');
  const jobs = useResource<OpportunityPage>('/v2/opportunities?page_size=5&sort=newest', view === 'overview');
  const applications = useResource<Application[]>(
    '/applications',
    ['overview', 'applications'].includes(view) || !!search.get('opportunity'),
  );
  const documents = useResource<Document[]>('/documents', view === 'documents');
  const documentJobs = useResource<OpportunityPage>(
    '/v2/opportunities?page_size=50&sort=newest',
    view === 'documents',
  );
  const sources = useResource<Source[]>('/sources', view === 'sources');
  const events = useResource<AuditEvent[]>('/events', view === 'activity');
  const activityStatus = useResource<{ worker: WorkerStatus }>('/operations', view === 'activity');
  const tasks = useResource<Task[]>('/tasks', view === 'activity');
  const notifications = useResource<Notification[]>('/notifications');
  const notificationSettings = useResource<LegacyItem>('/notification-settings', true, 300_000);
  const health = useResource<Health>('/health', view === 'controls', 300_000);
  const detailId = search.get('opportunity');
  const detail = useResource<Opportunity>(`/opportunities/${encodeURIComponent(detailId || '')}`, !!detailId);
  useBrowserNotifications(
    notifications.data || [],
    notificationSettings.data || null,
    authenticated && !notifications.isPending,
  );
  useEffect(() => {
    if (checking) return;
    if (!session && pathname !== '/login' && pathname !== '/register') router.replace('/login');
    if (session && (pathname === '/login' || pathname === '/register')) router.replace('/overview');
  }, [session, checking, pathname, router]);
  useEffect(() => {
    document.title = `${view === 'discover' ? 'Internships' : view === 'recommended' ? 'Your matches' : view.charAt(0).toUpperCase() + view.slice(1)} · InternPilot`;
  }, [view]);
  useEffect(() => {
    const shortcut = (event: KeyboardEvent) => {
      if (event.isComposing || event.defaultPrevented) return;
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        setCommand((value) => !value);
      }
    };
    window.addEventListener('keydown', shortcut);
    return () => window.removeEventListener('keydown', shortcut);
  }, []);
  const perform: Perform = useCallback(
    async <T,>(key: string, action: () => Promise<T>, message: string) => {
      setBusy(key);
      try {
        const result = await action();
        await invalidate(key);
        notify(message);
        return result;
      } catch (reason) {
        notify(reason instanceof Error ? reason.message : 'Action could not complete.', true);
        return null;
      } finally {
        setBusy('');
      }
    },
    [invalidate, notify],
  );
  const discover = () =>
    perform(
      'discover',
      () => api('/discovery/run', 'POST', {}),
      'Discovery queued. Workers will check permitted sources.',
    );
  const prepare = (job: LegacyItem) =>
    perform(
      `prepare-${job.id}`,
      () => api('/applications', 'POST', { opportunity_id: job.id }),
      'Draft preparation queued. Review its progress in Applications.',
    );
  const generate = (job: LegacyItem, kind: string) =>
    perform(
      `doc-${kind}`,
      () => api('/documents/generate', 'POST', { opportunity_id: job.id, kind }),
      'Document generated from verified facts.',
    );
  const openJob = useCallback(
    (job: Opportunity) => {
      const params = new URLSearchParams(search.toString());
      params.set('opportunity', job.id);
      router.push(`${pathname}?${params}`, { scroll: false });
    },
    [router, pathname, search],
  );
  const closeJob = () => {
    const params = new URLSearchParams(search.toString());
    params.delete('opportunity');
    router.replace(`${pathname}${params.size ? '?' + params : ''}`, { scroll: false });
  };
  const save = (job: Opportunity) =>
    perform(
      `save-${job.id}`,
      () => api(`/saved/${job.id}`, job.saved ? 'DELETE' : 'POST'),
      job.saved ? 'Removed from saved opportunities.' : 'Saved to your shortlist.',
    );
  const stop = () =>
    perform(
      'stop',
      () => api('/emergency-stop', 'POST', { stopped: !policy.data?.emergency_stop }),
      policy.data?.emergency_stop
        ? 'Your activity can resume under its policy.'
        : 'Emergency stop enabled. New actions are paused.',
    );
  const signOut = () =>
    perform(
      'logout',
      async () => {
        await api('/auth/logout', 'POST', {});
        clear();
        router.replace('/login');
      },
      'Signed out.',
    );
  if (checking)
    return (
      <main className="boot">
        <span className="brand-symbol">
          <Waves size={24} />
        </span>
        <p>Opening your workspace…</p>
        <LoaderCircle size={20} className="spin" />
      </main>
    );
  const feedback = toast && (
    <div className={`toast ${toast.error ? 'error' : ''}`} role={toast.error ? 'alert' : 'status'}>
      <span>{toast.text}</span>
      <button className="icon-btn" aria-label="Dismiss notification" onClick={() => setToast(null)}>
        <X size={16} />
      </button>
    </div>
  );
  if (!session && pathname !== '/login' && pathname !== '/register')
    return (
      <main className="boot">
        <LoaderCircle size={20} className="spin" />
        <p>Opening sign in…</p>
      </main>
    );
  if (!session)
    return (
      <>
        <Auth onLogin={(value) => login(value as import('@/lib/api-types').Session)} notify={notify} />
        {feedback}
      </>
    );
  const overviewQueries = [dashboard, jobs, applications];
  const activeQueries =
    view === 'overview'
      ? overviewQueries
      : view === 'applications'
        ? [applications]
        : view === 'documents'
          ? [documents, documentJobs]
          : view === 'sources'
            ? [sources]
            : view === 'activity'
              ? [events, tasks, activityStatus]
              : view === 'notifications'
                ? [notifications]
                : view === 'controls'
                  ? [health]
                  : [];
  const failed = [profile, policy, ...activeQueries].find((query) => query.isError);
  const pending = [profile, policy, ...activeQueries].some((query) => query.isPending);
  const renderJob = (raw: Opportunity) => (
    <OpportunityRowBridge key={raw.id} job={raw} busy={busy} onOpen={openJob} onSave={save} />
  );
  return (
    <>
      <WorkspaceShell
        view={view}
        session={session}
        name={profile.data?.name}
        stopped={!!policy.data?.emergency_stop}
        unread={(notifications.data || []).filter((n) => !n.read).length}
        onCommand={() => setCommand(true)}
        onSignOut={signOut}
      >
        {policy.data?.emergency_stop && (
          <div className="banner danger" role="status">
            <Pause size={17} />
            <span>Emergency stop is active. New discovery and external actions are paused.</span>
            <Button size="sm" variant="outline" onClick={stop} disabled={!!busy}>
              Resume
            </Button>
          </div>
        )}
        {failed ? (
          <div className="resource-error" role="alert">
            <XCircle size={24} />
            <h1>This view couldn’t load.</h1>
            <p>{failed.error?.message}</p>
            <Button onClick={() => failed.refetch()}>
              <RefreshCw size={15} />
              Try again
            </Button>
          </div>
        ) : pending ? (
          <Skeleton rows={5} />
        ) : (
          <>
            {view === 'overview' && (
              <Overview
                profile={profile.data}
                dashboard={dashboard.data}
                jobs={jobs.data?.items || []}
                applications={applications.data || []}
                sources={dashboard.data?.source_health || []}
                busy={busy}
                stopped={!!policy.data?.emergency_stop}
                onDiscover={discover}
                onOpen={openJob}
                onSave={save}
              />
            )}
            {['discover', 'hackathons', 'recommended', 'saved'].includes(view) && (
              <>
                <div className="explore-tabs" aria-label="Explore opportunities">
                  {(['discover', 'hackathons', 'recommended'] as const).map((id) => (
                    <Link
                      prefetch={false}
                      key={id}
                      href={routes[id]}
                      aria-current={view === id ? 'page' : undefined}
                    >
                      {id === 'discover'
                        ? 'Internships'
                        : id === 'hackathons'
                          ? 'Hackathons'
                          : 'Your matches'}
                    </Link>
                  ))}
                </div>
                <Explorer
                  key={`${session.user.id}:${view}`}
                  mode={
                    view === 'discover'
                      ? 'internship'
                      : view === 'hackathons'
                        ? 'hackathon'
                        : (view as 'recommended' | 'saved')
                  }
                  workspaceId={session.user.id}
                  api={api}
                  busy={!!busy}
                  stopped={!!policy.data?.emergency_stop}
                  refreshKey={0}
                  onDiscover={discover}
                  onPreferencesChanged={() => invalidate('profile')}
                  localCities={profile.data?.preferred_local_cities || ['Nagpur', 'Pune']}
                  renderJob={renderJob}
                />
              </>
            )}
            {view === 'applications' && (
              <Applications
                applications={applications.data || []}
                busy={busy}
                perform={perform}
                onExplore={() => router.push(routes.discover)}
                onJob={(id) => openJob({ id, title: '', company: '' })}
              />
            )}
            {view === 'documents' && (
              <Documents
                documents={documents.data || []}
                jobs={documentJobs.data?.items || []}
                busy={busy}
                perform={perform}
              />
            )}
            {view === 'profile' && (
              <ProfileView
                initial={profile.data!}
                busy={busy === 'profile'}
                onSave={(value) =>
                  perform(
                    'profile',
                    () => api('/profile', 'PUT', value),
                    'Profile saved. Only your verified facts are used.',
                  ).then(() => {})
                }
              />
            )}
            {view === 'controls' && (
              <PolicyView
                initial={policy.data || {}}
                busy={!!busy}
                onStop={stop}
                health={health.data || {}}
                onSave={(value) =>
                  perform('policy', () => api('/policy', 'PUT', value), 'Application policies saved.').then(
                    () => {},
                  )
                }
                demo={() =>
                  perform(
                    'demo',
                    () => api('/demo/run', 'POST', {}),
                    'Local test queued. No real employer receives an application.',
                  )
                }
                seed={() =>
                  perform('seed', () => api('/demo/seed', 'POST', {}), 'Labeled local test records added.')
                }
              />
            )}
            {view === 'sources' && <Sources sources={sources.data || []} busy={busy} perform={perform} />}
            {view === 'notifications' && (
              <Notifications
                settings={notificationSettings.data || null}
                api={api}
                notify={notify}
                onSettings={updateNotificationSettings}
                refreshKey={0}
                notifications={notifications.data || []}
                jobs={[]}
                busy={busy}
                onOpen={(value) => openJob(value as Opportunity)}
                onRead={(value) =>
                  perform(
                    'notification',
                    () => api(`/notifications/${value.id}`, 'PATCH', { read: true }),
                    'Marked as read.',
                  )
                }
              />
            )}
            {view === 'activity' && (
              <>
                <PageTitle
                  kicker=""
                  title="Activity & logs"
                  description="Recorded worker tasks, events and outcome evidence."
                />
                <WorkerSummary worker={activityStatus.data?.worker || {}} />
                <section className="panel">
                  <div className="panel-head">
                    <h2>Task queue</h2>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() =>
                        Promise.all([tasks.refetch(), events.refetch(), activityStatus.refetch()])
                      }
                    >
                      <RefreshCw size={14} />
                      Refresh
                    </Button>
                  </div>
                  {tasks.data?.length ? (
                    <div className="quiet-table-wrap">
                      <table className="quiet-table">
                        <thead>
                          <tr>
                            <th>Task</th>
                            <th>Status</th>
                            <th>Attempts</th>
                            <th>Last update</th>
                            <th>Details</th>
                          </tr>
                        </thead>
                        <tbody>
                          {tasks.data.map((task) => (
                            <tr key={task.id}>
                              <td>{task.kind}</td>
                              <td>{task.status}</td>
                              <td>{task.attempts}</td>
                              <td>{new Date(task.updated_at).toLocaleString()}</td>
                              <td className="table-note">
                                {task.error || '—'}
                                {task.status === 'failed' &&
                                  ['discovery', 'gmail_sync'].includes(task.kind) && (
                                    <Button
                                      variant="outline"
                                      size="sm"
                                      disabled={!!busy}
                                      onClick={() =>
                                        perform(
                                          'task',
                                          () => api(`/tasks/${task.id}/requeue`, 'POST', {}),
                                          'Read-only task queued for retry.',
                                        )
                                      }
                                    >
                                      Retry read-only task
                                    </Button>
                                  )}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <p className="inline-empty">No tasks recorded yet.</p>
                  )}
                </section>
                <section className="panel mt-6">
                  <div className="panel-head">
                    <h2>Workspace events</h2>
                  </div>
                  <EventList events={events.data || []} />
                </section>
              </>
            )}
            {view === 'outreach' && <Outreach api={api} notify={notify} />}
            {view === 'automation' && (
              <Automation
                api={api}
                onPolicy={() => router.push(routes.controls)}
                onSources={() => router.push(routes.sources)}
                onActivity={() => router.push(routes.activity)}
              />
            )}
            {view === 'security' && (
              <Security
                api={api}
                onSession={(value) => login(value as import('@/lib/api-types').Session)}
                notify={notify}
              />
            )}
            {view === 'owner' &&
              (session.user.role === 'owner' ? (
                <Owner api={api} download={(path, body) => api(path, 'POST', body, true)} notify={notify} />
              ) : (
                <div className="empty">
                  <h1>Owner access required</h1>
                  <p>This console is available only to the workspace owner.</p>
                  <Link href={routes.overview}>Back to your workspace</Link>
                </div>
              ))}
          </>
        )}
        {['automation', 'sources', 'controls', 'activity'].includes(view) && (
          <nav className="automation-links" aria-label="Automation sections">
            {(['automation', 'sources', 'controls', 'activity'] as const).map((id) => (
              <Link
                prefetch={false}
                key={id}
                href={routes[id]}
                aria-current={id === view ? 'page' : undefined}
              >
                {id === 'automation'
                  ? 'Overview'
                  : id === 'sources'
                    ? 'Sources'
                    : id === 'controls'
                      ? 'Policies'
                      : 'Activity'}
              </Link>
            ))}
          </nav>
        )}
      </WorkspaceShell>
      <Modal
        open={!!detailId}
        onClose={closeJob}
        title={detail.data?.title || 'Opportunity details'}
        eyebrow={detail.data?.company}
        presentation="sheet"
      >
        {detail.isPending ? (
          <Skeleton />
        ) : detail.isError ? (
          <div className="empty" role="alert">
            <h3>Opportunity unavailable</h3>
            <p>{detail.error.message}</p>
            <Button variant="outline" onClick={() => detail.refetch()}>
              Try again
            </Button>
          </div>
        ) : (
          detail.data && (
            <JobDetail
              job={detail.data}
              policy={policy.data || {}}
              busy={busy}
              prepare={prepare}
              generate={generate}
              applications={applications.data || []}
              onSave={() => save(detail.data!)}
            />
          )
        )}
      </Modal>
      {command && (
        <CommandMenu
          open={command}
          onClose={() => setCommand(false)}
          onOpen={openJob}
          owner={session.user.role === 'owner'}
        />
      )}
      {feedback}
    </>
  );
}

import { OpportunityRow } from '@/components/opportunity-row';
function OpportunityRowBridge({
  job,
  busy,
  onOpen,
  onSave,
}: {
  job: Opportunity;
  busy: string;
  onOpen: (job: Opportunity) => void;
  onSave: (job: Opportunity) => void;
}) {
  return (
    <OpportunityRow
      job={job}
      onClick={() => onOpen(job)}
      onSave={() => onSave(job)}
      saving={busy === `save-${job.id}`}
      saveDisabled={!!busy}
    />
  );
}

'use client';
import { useState } from 'react';

import { ArrowUpRight, Bell, Check } from 'lucide-react';

import { NotificationSettings } from '@/components/notification-settings';
import { api } from '@/lib/api-client';
import type { LegacyItem as Item } from '@/lib/legacy-types';
import { timestamp, human } from '@/features/shared/format';
import { Empty, PageTitle } from '@/features/shared/primitives';
export function NotificationList({
  notifications,
  jobs,
  busy,
  onOpen,
  onRead,
}: {
  notifications: Item[];
  jobs: Item[];
  busy: string;
  onOpen: (job: Item) => void;
  onRead: (notification: Item) => void;
}) {
  return notifications.length ? (
    <div className="notifications-list">
      {notifications.map((notification) => {
        const job =
          jobs.find((item) => item.id === notification.opportunity_id) ||
          (notification.opportunity_id ? { id: notification.opportunity_id } : undefined);
        return (
          <div
            key={notification.id}
            className={`notification-item ${notification.read || notification.read_at ? '' : 'unread'}`}
          >
            <div className="event-icon">
              <Bell size={17} />
            </div>
            <div>
              <strong>{notification.title || human(notification.kind || 'Workspace update')}</strong>
              <p>{notification.message || notification.body || notification.detail || ''}</p>
              <small>{timestamp(notification.created_at)}</small>
              {job && (
                <button className="text-link notification-action" onClick={() => onOpen(job)}>
                  View opportunity
                  <ArrowUpRight size={13} />
                </button>
              )}
            </div>
            {!notification.read && !notification.read_at && (
              <button
                className="icon-btn"
                disabled={!!busy}
                aria-label="Mark as read"
                onClick={() => onRead(notification)}
              >
                <Check size={17} />
              </button>
            )}
          </div>
        );
      })}
    </div>
  ) : (
    <Empty icon={Bell} title="You’re all caught up">
      Matches, deadline reminders, and application updates will appear here.
    </Empty>
  );
}
export function NotificationsView(props: {
  notifications: Item[];
  jobs: Item[];
  busy: string;
  onOpen: (job: Item) => void;
  onRead: (notification: Item) => void;
  settings: Item | null;
  api: typeof api;
  notify: (message: string, error?: boolean) => void;
  onSettings: (settings: Item) => void;
  refreshKey: number;
}) {
  const [unreadOnly, setUnreadOnly] = useState(false);
  const unread = props.notifications.filter((item) => !item.read && !item.read_at).length;
  return (
    <>
      <PageTitle
        kicker="STAY CLOSE TO YOUR NEXT STEP"
        title="Notifications"
        description="Review new matches, upcoming deadlines, and application progress in one place."
      />
      <div className="tabs-line">
        <button className={!unreadOnly ? 'selected' : ''} onClick={() => setUnreadOnly(false)}>
          All updates<span>{props.notifications.length}</span>
        </button>
        <button className={unreadOnly ? 'selected' : ''} onClick={() => setUnreadOnly(true)}>
          Unread<span>{unread}</span>
        </button>
      </div>
      <section className="panel notification-center">
        <NotificationList
          {...props}
          notifications={
            unreadOnly
              ? props.notifications.filter((item) => !item.read && !item.read_at)
              : props.notifications
          }
        />
      </section>
      <NotificationSettings
        initial={props.settings}
        api={props.api}
        notify={props.notify}
        onSettings={props.onSettings}
        refreshKey={props.refreshKey}
      />
    </>
  );
}

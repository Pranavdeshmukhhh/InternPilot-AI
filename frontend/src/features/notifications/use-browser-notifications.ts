'use client';
import { useEffect, useRef } from 'react';
import type { Notification as Notice } from '@/lib/api-types';
export type BrowserSettings = {
  browser_enabled?: boolean;
  quiet_hours_enabled?: boolean;
  timezone?: string;
  quiet_start?: string;
  quiet_end?: string;
};
function quietNow(settings: BrowserSettings) {
  if (!settings.quiet_hours_enabled || !settings.quiet_start || !settings.quiet_end) return false;
  try {
    const current = new Intl.DateTimeFormat('en-GB', {
      timeZone: settings.timezone || 'Asia/Kolkata',
      hour: '2-digit',
      minute: '2-digit',
      hourCycle: 'h23',
    }).format(new Date());
    return settings.quiet_start < settings.quiet_end
      ? current >= settings.quiet_start && current < settings.quiet_end
      : settings.quiet_start > settings.quiet_end
        ? current >= settings.quiet_start || current < settings.quiet_end
        : false;
  } catch {
    return false;
  }
}
export function useBrowserNotifications(
  notifications: Notice[],
  settings: BrowserSettings | null,
  active: boolean,
) {
  const known = useRef<Set<string> | null>(null);
  useEffect(() => {
    if (!active) {
      known.current = null;
      return;
    }
    if (!known.current) {
      known.current = new Set(notifications.map((item) => item.id));
      return;
    }
    const fresh = notifications.filter((item) => !known.current?.has(item.id));
    for (const item of notifications) known.current.add(item.id);
    if (
      !settings?.browser_enabled ||
      typeof Notification === 'undefined' ||
      Notification.permission !== 'granted' ||
      quietNow(settings)
    )
      return;
    for (const item of fresh.filter((item) => !item.read && !item.read_at)) {
      try {
        const notification = new Notification('InternPilot update', {
          body: item.message || '',
          tag: `internpilot-${item.id}`,
        });
        notification.onclick = () => {
          window.focus();
          notification.close();
        };
      } catch {
        /* Some mobile browsers require a service worker for system notifications. In-app notices remain available. */
      }
    }
  }, [notifications, settings, active]);
}

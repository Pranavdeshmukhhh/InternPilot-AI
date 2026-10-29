'use client';

import { useEffect, useState, type FormEvent } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { Bell, Check, Clock3, LoaderCircle, Mail, MessageCircle, RefreshCw, Send, X } from 'lucide-react';
import { Button } from '@/components/ui/button';

type Item = Record<string, any>;
type Api = (path: string, method?: string, body?: unknown) => Promise<any>;
const defaults: Item = {
  browser_enabled: false,
  email_enabled: false,
  email_to: '',
  telegram_enabled: false,
  telegram_chat_id: '',
  whatsapp_enabled: false,
  whatsapp_to: '',
  quiet_hours_enabled: false,
  quiet_start: '22:00',
  quiet_end: '08:00',
  timezone: 'Asia/Kolkata',
};
const keys = Object.keys(defaults);
export { useBrowserNotifications } from '@/features/notifications/use-browser-notifications';

export function NotificationSettings({
  initial,
  api,
  notify,
  onSettings,
  refreshKey,
}: {
  initial: Item | null;
  api: Api;
  notify: (message: string, error?: boolean) => void;
  onSettings: (settings: Item) => void;
  refreshKey: number;
}) {
  const [settings, setSettings] = useState<Item>(initial || defaults);
  const [loading, setLoading] = useState(!initial);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState('');
  const [deliveries, setDeliveries] = useState<Item[]>([]);
  const [deliveriesLoading, setDeliveriesLoading] = useState(true);
  const [deliveryError, setDeliveryError] = useState('');
  const [review, setReview] = useState<Item | null>(null);
  const [consent, setConsent] = useState(false);
  const [reload, setReload] = useState(0);
  useEffect(() => {
    let mounted = true;
    api('/notification-settings')
      .then((result) => {
        if (mounted) {
          setSettings({ ...defaults, ...result });
          onSettings(result);
          setError('');
        }
      })
      .catch((reason) => {
        if (mounted) setError(reason.message);
      })
      .finally(() => {
        if (mounted) setLoading(false);
      });
    return () => {
      mounted = false;
    };
  }, [api, onSettings]);
  useEffect(() => {
    let mounted = true;
    setDeliveriesLoading(true);
    api('/notification-deliveries')
      .then((result) => {
        if (mounted) {
          setDeliveries(Array.isArray(result) ? result : result.items || []);
          setDeliveryError('');
        }
      })
      .catch((reason) => {
        if (mounted) setDeliveryError(reason.message);
      })
      .finally(() => {
        if (mounted) setDeliveriesLoading(false);
      });
    return () => {
      mounted = false;
    };
  }, [api, refreshKey, reload]);
  const set = (key: string, value: any) => setSettings((current) => ({ ...current, [key]: value }));
  const save = async (event: FormEvent) => {
    event.preventDefault();
    setBusy('settings');
    try {
      const payload = Object.fromEntries(keys.map((key) => [key, settings[key]]));
      const result = await api('/notification-settings', 'PUT', payload);
      setSettings({ ...defaults, ...result });
      onSettings(result);
      notify('Notification preferences saved. Outbound messages still require your review.');
    } catch (reason) {
      notify((reason as Error).message, true);
    } finally {
      setBusy('');
    }
  };
  const browserToggle = async (enabled: boolean) => {
    if (!enabled) {
      set('browser_enabled', false);
      return;
    }
    if (typeof Notification === 'undefined') {
      notify('This browser does not support desktop notifications.', true);
      return;
    }
    const permission = await Notification.requestPermission();
    if (permission !== 'granted') {
      notify(
        'Browser notification permission was not granted. You can change it in your browser settings.',
        true,
      );
      return;
    }
    set('browser_enabled', true);
  };
  const config = settings.delivery_config || {};
  const deliveryTime = (value: string) => (value ? new Date(value).toLocaleString() : 'Not recorded');

  return (
    <>
      <form onSubmit={save} className="notification-settings-form">
        <section className="panel form-section mt-6">
          <div className="form-section-intro">
            <span className="form-section-icon">
              <Bell size={20} />
            </span>
            <h2>Notification preferences</h2>
            <p>
              In-app updates are always available. Choose optional channels and quiet hours for your
              workspace.
            </p>
          </div>
          <div>
            {loading ? (
              <p className="muted">Loading notification preferences…</p>
            ) : error ? (
              <p className="muted" role="alert">
                {error}
              </p>
            ) : (
              <>
                <label className="check-label">
                  <input
                    type="checkbox"
                    checked={!!settings.browser_enabled}
                    disabled={!!busy}
                    onChange={(event) => void browserToggle(event.target.checked)}
                  />
                  Browser notifications
                </label>
                <p className="field-hint channel-hint">
                  Shows new updates while this workspace is open, with your browser’s permission.
                </p>
                {(['email', 'telegram', 'whatsapp'] as const).map((channel) => {
                  const name =
                    channel === 'email' ? 'Email' : channel === 'telegram' ? 'Telegram' : 'WhatsApp';
                  const destination =
                    channel === 'email'
                      ? 'email_to'
                      : channel === 'telegram'
                        ? 'telegram_chat_id'
                        : 'whatsapp_to';
                  return (
                    <div className="notification-channel" key={channel}>
                      <label className="check-label">
                        <input
                          type="checkbox"
                          disabled={!!busy || !config[channel]}
                          checked={!!settings[`${channel}_enabled`]}
                          onChange={(event) => set(`${channel}_enabled`, event.target.checked)}
                        />
                        {name} delivery
                      </label>
                      <p className="field-hint">
                        {config[channel]
                          ? 'Messages wait for your review and explicit approval before sending.'
                          : 'This channel is unavailable until its provider is configured by the workspace operator.'}
                      </p>
                      <label className="field">
                        <span className="field-label">
                          {channel === 'email'
                            ? 'Destination email'
                            : channel === 'telegram'
                              ? 'Telegram chat ID'
                              : 'WhatsApp phone number'}
                        </span>
                        <input
                          type={channel === 'email' ? 'email' : 'text'}
                          value={settings[destination] || ''}
                          disabled={!!busy || !config[channel]}
                          required={!!settings[`${channel}_enabled`]}
                          onChange={(event) => set(destination, event.target.value)}
                          placeholder={
                            channel === 'email'
                              ? 'you@example.com'
                              : channel === 'whatsapp'
                                ? '+91…'
                                : 'Your authorized chat ID'
                          }
                        />
                      </label>
                    </div>
                  );
                })}
                <div className="notification-quiet-hours">
                  <label className="check-label">
                    <input
                      type="checkbox"
                      checked={!!settings.quiet_hours_enabled}
                      disabled={!!busy}
                      onChange={(event) => set('quiet_hours_enabled', event.target.checked)}
                    />
                    Enable quiet hours
                  </label>
                  <div className="form-grid">
                    <label className="field">
                      <span className="field-label">Quiet hours start</span>
                      <input
                        type="time"
                        disabled={!settings.quiet_hours_enabled || !!busy}
                        required
                        value={settings.quiet_start}
                        onChange={(event) => set('quiet_start', event.target.value)}
                      />
                    </label>
                    <label className="field">
                      <span className="field-label">Quiet hours end</span>
                      <input
                        type="time"
                        disabled={!settings.quiet_hours_enabled || !!busy}
                        required
                        value={settings.quiet_end}
                        onChange={(event) => set('quiet_end', event.target.value)}
                      />
                    </label>
                  </div>
                  <label className="field">
                    <span className="field-label">Time zone</span>
                    <input
                      required
                      value={settings.timezone}
                      disabled={!!busy}
                      onChange={(event) => set('timezone', event.target.value)}
                      placeholder="Asia/Kolkata"
                    />
                    <span className="field-hint">
                      Use an IANA time zone such as Asia/Kolkata or Europe/London.
                    </span>
                  </label>
                </div>
              </>
            )}
          </div>
        </section>
        <div className="save-bar">
          <span>
            <Clock3 size={14} />
            Quiet hours pause optional notification delivery.
          </span>
          <Button type="submit" disabled={loading || !!error || !!busy}>
            {busy === 'settings' ? <LoaderCircle className="spin" size={15} /> : <Check size={15} />}Save
            notification preferences
          </Button>
        </div>
      </form>
      <section className="panel">
        <div className="panel-head">
          <div>
            <h2>Outbound message review</h2>
            <p>Preview each message and destination. Only an explicit approval can send it.</p>
          </div>
          <Button
            variant="outline"
            size="sm"
            disabled={deliveriesLoading}
            onClick={() => setReload((value) => value + 1)}
          >
            <RefreshCw size={14} className={deliveriesLoading ? 'spin' : ''} />
            Refresh
          </Button>
        </div>
        {deliveryError && (
          <div className="banner danger">
            <span>{deliveryError}</span>
          </div>
        )}
        {!deliveries.length ? (
          <div className="quiet-empty">
            <Send size={18} />
            <span>
              {deliveriesLoading
                ? 'Checking outbound messages…'
                : 'No outbound messages are waiting for review.'}
            </span>
          </div>
        ) : (
          <div className="delivery-list">
            {deliveries.map((delivery) => (
              <div className="delivery-row" key={delivery.id}>
                <div className="event-icon">
                  {delivery.channel === 'email' ? <Mail size={17} /> : <MessageCircle size={17} />}
                </div>
                <div>
                  <strong>
                    {delivery.channel === 'email'
                      ? 'Email'
                      : delivery.channel === 'telegram'
                        ? 'Telegram'
                        : 'WhatsApp'}{' '}
                    · {delivery.destination_masked || delivery.destination || 'Destination unavailable'}
                  </strong>
                  <p>{delivery.message}</p>
                  <small>
                    {deliveryTime(delivery.created_at)} · {String(delivery.status).replaceAll('_', ' ')}
                  </small>
                  {delivery.not_before && <small>Available after {deliveryTime(delivery.not_before)}</small>}
                  {delivery.last_error && <p className="delivery-error">{delivery.last_error}</p>}
                </div>
                {delivery.status === 'draft' && (
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={!!busy}
                    onClick={() => {
                      setConsent(false);
                      setReview(delivery);
                    }}
                  >
                    Review message
                  </Button>
                )}
              </div>
            ))}
          </div>
        )}
      </section>
      <Dialog.Root
        open={!!review}
        onOpenChange={(open) => {
          if (!open) setReview(null);
        }}
      >
        <Dialog.Portal>
          <Dialog.Overlay className="modal-overlay" />
          <Dialog.Content className="modal">
            <div className="modal-head">
              <div>
                <p className="eyebrow">ONE MESSAGE. YOUR APPROVAL.</p>
                <Dialog.Title>Review outbound message</Dialog.Title>
                <Dialog.Description className="sr-only">
                  Review the channel, destination, and exact message before authorizing delivery.
                </Dialog.Description>
              </div>
              <Dialog.Close className="icon-btn" aria-label="Close dialog">
                <X size={20} />
              </Dialog.Close>
            </div>
            {review && (
              <div className="modal-body">
                <div className="detail-facts">
                  <div>
                    <span>Channel</span>
                    <strong>{review.channel}</strong>
                  </div>
                  <div>
                    <span>Destination</span>
                    <strong>
                      {review.destination_masked || review.destination || 'Destination unavailable'}
                    </strong>
                  </div>
                  <div>
                    <span>Delivery status</span>
                    <strong>{String(review.status).replaceAll('_', ' ')}</strong>
                  </div>
                </div>
                <div className="outbound-message-preview">{review.message}</div>
                {review.not_before && (
                  <p className="field-hint">
                    Quiet hours or retry timing: available after {deliveryTime(review.not_before)}.
                  </p>
                )}
                <label className="consent-box">
                  <input
                    type="checkbox"
                    checked={consent}
                    onChange={(event) => setConsent(event.target.checked)}
                  />
                  <span>I approve sending this exact message to the destination shown above.</span>
                </label>
                <Button
                  className="w-full"
                  disabled={
                    !consent ||
                    !!busy ||
                    !(review.destination_masked || review.destination) ||
                    (!!review.not_before && new Date(review.not_before).getTime() > Date.now())
                  }
                  onClick={async () => {
                    setBusy('delivery');
                    try {
                      await api(`/notification-deliveries/${review.id}/send`, 'POST', { consent: true });
                      notify('Message delivery request completed. Check the delivery status below.');
                      setReview(null);
                      setReload((value) => value + 1);
                    } catch (reason) {
                      notify((reason as Error).message, true);
                    } finally {
                      setBusy('');
                    }
                  }}
                >
                  <Send size={15} />
                  Approve and send this message
                </Button>
              </div>
            )}
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </>
  );
}

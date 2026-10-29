'use client';

import { useEffect, useState } from 'react';
import { ExternalLink, LoaderCircle, Plus, X } from 'lucide-react';
import { Button } from '@/components/ui/button';

type Candidate = {
  id: string;
  kind: string;
  slug: string;
  url: string | null;
  company: string;
  evidence_url: string;
  discovered_at: string;
  reason: string;
  verified: false;
};
type Props = { api: (path: string, method?: string, body?: unknown) => Promise<any>; onChanged: () => void };

export function SourceCandidates({ api, onChanged }: Props) {
  const [items, setItems] = useState<Candidate[]>([]);
  const [total, setTotal] = useState(0);
  const [consent, setConsent] = useState<Record<string, boolean>>({});
  const [pending, setPending] = useState('');
  const [error, setError] = useState('');
  const [loaded, setLoaded] = useState(false);
  const [reload, setReload] = useState(0);
  const [message, setMessage] = useState('');
  useEffect(() => {
    let current = true;
    api('/discovery/source-candidates')
      .then((result) => {
        if (current) {
          setItems(result.items);
          setTotal(result.total);
          setLoaded(true);
          setError('');
        }
      })
      .catch((reason) => {
        if (current) {
          setError(reason.message);
          setLoaded(true);
        }
      });
    return () => {
      current = false;
    };
  }, [api, reload]);
  const act = async (item: Candidate, action: 'install' | 'dismiss') => {
    setPending(item.id);
    setError('');
    setMessage('');
    try {
      await api(
        `/discovery/source-candidates/${item.id}/${action}`,
        'POST',
        action === 'install' ? { permitted: true } : undefined,
      );
      setItems((rows) => rows.filter((row) => row.id !== item.id));
      setTotal((value) => Math.max(0, value - 1));
      setMessage(
        action === 'install'
          ? 'Source enabled for read-only scans. Its first scan will establish whether the connector works.'
          : 'Source suggestion dismissed.',
      );
      onChanged();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Unable to update source suggestion.');
    } finally {
      setPending('');
    }
  };
  return (
    <details className="regional-discovery">
      <summary>New employer & program sources{loaded && total > 0 ? ` · ${total}` : ''}</summary>
      <p>
        Searches can uncover smaller employers, university programs and public career pages beyond your
        connected boards. These links need review; employer identity, vacancies and access permission are
        unverified.
      </p>
      <Button
        variant="outline"
        size="sm"
        disabled={!!pending}
        onClick={() => setReload((value) => value + 1)}
      >
        Refresh suggestions
      </Button>
      {!loaded && (
        <p role="status">
          <LoaderCircle size={14} className="spin" />
          Loading discovered sources…
        </p>
      )}
      {loaded && !items.length && !error && (
        <p className="footnote">
          No source suggestions awaiting review. Enable regional search and run discovery, or add a permitted
          public source directly.
        </p>
      )}
      <div className="operational-list">
        {items.map((item) => (
          <div key={item.id} className="flex-col sm:flex-row">
            <div className="min-w-0 break-words">
              <strong>{item.company}</strong>
              <small>
                {item.kind} · {item.slug || item.url}
              </small>
              <small>{item.reason}</small>
              <a href={item.evidence_url} target="_blank" rel="noopener noreferrer">
                Review publisher <ExternalLink size={12} className="inline" />
              </a>
              {item.kind === 'html' && (
                <small>
                  Scans structured job/event data and a bounded set of linked opportunities. Plain links
                  remain unverified; PDF-only or unsupported pages need manual review.
                </small>
              )}
              <label className="check-label">
                <input
                  type="checkbox"
                  checked={!!consent[item.id]}
                  onChange={(event) => setConsent((value) => ({ ...value, [item.id]: event.target.checked }))}
                />
                I reviewed this source and confirm read-only automated access is permitted.
              </label>
            </div>
            <div className="flex shrink-0 flex-wrap items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={!!pending || !consent[item.id]}
                onClick={() => act(item, 'install')}
              >
                <Plus size={13} />
                Enable source
              </Button>
              <Button
                variant="ghost"
                size="sm"
                disabled={!!pending}
                aria-label={`Dismiss ${item.company}`}
                onClick={() => act(item, 'dismiss')}
              >
                <X size={13} />
                Dismiss
              </Button>
            </div>
          </div>
        ))}
      </div>
      {total > items.length && (
        <p className="footnote">
          Showing {items.length} of {total} suggestions. Review these and refresh to see more.
        </p>
      )}
      {message && <p role="status">{message}</p>}
      {error && (
        <p className="banner danger" role="alert">
          {error}
        </p>
      )}
    </details>
  );
}

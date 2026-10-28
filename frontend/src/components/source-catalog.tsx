'use client';

import { useEffect, useState } from 'react';
import { Plus } from 'lucide-react';
import { Button } from '@/components/ui/button';

type Entry = { key: string; label: string; coverage: string; installed: boolean; requires_key: boolean; verified_at: string | null };
export function SourceCatalog({ api, onChanged }: { api: (path: string, method?: string, body?: unknown) => Promise<any>; onChanged: () => void }) {
  const [entries, setEntries] = useState<Entry[]>([]);
  const [error, setError] = useState('');
  const [pending, setPending] = useState('');
  useEffect(() => { let current = true; api('/sources/catalog').then(value => { if (current) setEntries(value); }).catch(reason => { if (current) setError(reason.message); }); return () => { current = false; }; }, [api]);
  return <details className="regional-discovery"><summary>India source catalog</summary><div className="operational-list">{entries.map(entry => <div key={entry.key}><div><strong>{entry.label}</strong><small>{entry.coverage}</small><small>{entry.verified_at ? `Public API checked ${entry.verified_at}; availability can change.` : 'Search configuration; live search requires your provider key.'}</small></div><Button variant="outline" size="sm" disabled={entry.installed || entry.requires_key || !!pending} onClick={async () => { setPending(entry.key); setError(''); try { await api('/sources/catalog/' + entry.key, 'POST'); setEntries(rows => rows.map(row => row.key === entry.key ? { ...row, installed: true } : row)); onChanged(); } catch (reason) { setError(reason instanceof Error ? reason.message : 'Source unavailable.'); } finally { setPending(''); } }}><Plus size={13} />{entry.installed ? 'Added' : entry.requires_key ? 'Search key needed' : 'Add source'}</Button></div>)}</div>{error && <p className="banner danger" role="alert">{error}</p>}</details>;
}

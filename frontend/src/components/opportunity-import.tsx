'use client';

import { useState, type FormEvent } from 'react';
import { FileUp, LoaderCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';

type ImportResult = { added: number; updated: number; skipped: number };
type Props = {
  api: (path: string, method?: string, body?: unknown) => Promise<ImportResult>;
  onImported: () => Promise<unknown>;
};

export function OpportunityImport({ api, onImported }: Props) {
  const [provider, setProvider] = useState('jobspy');
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [error, setError] = useState('');
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!file) return;
    setBusy(true); setError(''); setResult(null);
    try {
      const form = new FormData(); form.append('file', file);
      const imported = await api(`/imports/opportunities?provider=${provider}`, 'POST', form);
      setResult(imported);
      await onImported();
    } catch (reason) { setError((reason as Error).message); }
    finally { setBusy(false); }
  };
  return <section className="panel form-section mb-6">
    <div className="form-section-intro"><span className="form-section-icon"><FileUp size={20} /></span><h2>Import opportunity references</h2><p>Bring an authorized JobSpy export or InternScan JSON feed into this workspace. Duplicate employer links are merged; official verification stays visible.</p></div>
    <form onSubmit={submit}>
      <div className="form-grid"><label className="field"><span className="field-label">Export format</span><select value={provider} onChange={event => setProvider(event.target.value)}><option value="jobspy">JobSpy CSV / JSON / JSONL</option><option value="internscan">InternScan JSON</option></select></label>
        <label className="field"><span className="field-label">Opportunity export file</span><input type="file" accept=".csv,.json,.jsonl" required disabled={busy} onChange={event => setFile(event.target.files?.[0] || null)} /><span className="field-hint">Public opportunity metadata only, up to 8 MiB and 2,000 records.</span></label></div>
      <Button type="submit" variant="outline" disabled={!file || busy}>{busy ? <LoaderCircle size={16} className="spin" /> : <FileUp size={16} />}Import opportunities</Button>
      {error && <p role="alert" className="mt-4">{error}</p>}
      {result && <p role="status" className="mt-4">{result.added} new references · {result.updated} duplicates updated · {result.skipped} unsupported records skipped. Imported links require employer verification.</p>}
    </form>
  </section>;
}

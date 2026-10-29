'use client';
import { useState, useRef } from 'react';

import {
  ArrowDownToLine,
  BookOpen,
  FilePlus2,
  FileText,
  LoaderCircle,
  LockKeyhole,
  Plus,
  UploadCloud,
  X,
} from 'lucide-react';
import { Button } from '@/components/ui/button';

import { api } from '@/lib/api-client';
import type { LegacyItem as Item, Perform } from '@/lib/legacy-types';
import { timestamp, human } from '@/features/shared/format';
import { Empty, Field, PageTitle } from '@/features/shared/primitives';
export function DocumentsView({
  documents,
  jobs,
  busy,
  perform,
}: {
  documents: Item[];
  jobs: Item[];
  busy: string;
  perform: Perform;
}) {
  const [proposal, setProposal] = useState<Item | null>(null);
  const [opportunity, setOpportunity] = useState('');
  const [kind, setKind] = useState('resume');
  const input = useRef<HTMLInputElement>(null);
  const upload = async (file?: File) => {
    if (!file) return;
    if (file.size > 10 * 1024 * 1024) {
      setProposal({ error: 'Choose a file smaller than 10 MB.' });
      return;
    }
    const form = new FormData();
    form.append('file', file);
    const r = await perform(
      'upload',
      () => api('/documents/upload', 'POST', form),
      'Original document uploaded securely. Parsed fields remain unverified.',
    );
    if (r) setProposal(r);
    if (input.current) input.current.value = '';
  };
  return (
    <>
      <PageTitle
        kicker="ACCURACY IN EVERY WORD"
        title="Resume studio"
        description="Secure originals, tailored PDFs, and a version history built from verified facts."
        action={
          <Button disabled={!!busy} onClick={() => input.current?.click()}>
            <UploadCloud size={16} />
            Upload resume
          </Button>
        }
      />
      <input
        className="sr-only"
        type="file"
        ref={input}
        accept=".pdf,.txt,.docx"
        onChange={(e) => upload(e.target.files?.[0])}
        aria-label="Upload original resume"
      />
      <div className="documents-top">
        <section className="upload-panel">
          <div className="empty-icon">
            <UploadCloud size={25} strokeWidth={1.5} />
          </div>
          <h3>Start with your original resume</h3>
          <p>
            Upload a PDF, DOCX, or TXT file. Extracted suggestions are kept separate until you review and
            verify them in your profile.
          </p>
          <Button variant="outline" onClick={() => input.current?.click()} disabled={!!busy}>
            {busy === 'upload' ? <LoaderCircle size={15} className="spin" /> : <Plus size={15} />}Choose a
            document
          </Button>
          <span className="file-support">PDF, DOCX, TXT · Up to 10 MB</span>
        </section>
        <section className="panel generate-panel">
          <div className="panel-head">
            <div>
              <h2>Tailor an application document</h2>
              <p>Relevant facts, never invented achievements.</p>
            </div>
            <BookOpen size={19} className="muted" />
          </div>
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              await perform(
                'generate',
                () => api('/documents/generate', 'POST', { opportunity_id: opportunity, kind }),
                'Tailored PDF generated. Download it from the version history.',
              );
            }}
          >
            <Field label="Target opportunity">
              <select value={opportunity} required onChange={(e) => setOpportunity(e.target.value)}>
                <option value="">Choose an opportunity</option>
                {jobs.map((j) => (
                  <option key={j.id} value={j.id}>
                    {j.company} · {j.title}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Document type">
              <select value={kind} onChange={(e) => setKind(e.target.value)}>
                <option value="resume">ATS-compatible resume</option>
                <option value="cover_letter">Concise cover letter</option>
              </select>
            </Field>
            <Button variant="outline" type="submit" disabled={!!busy || !opportunity}>
              <FilePlus2 size={15} />
              Generate PDF
            </Button>
          </form>
        </section>
      </div>
      {proposal && (
        <section className="panel proposal-panel">
          <div className="panel-head">
            <div>
              <h2>Resume extraction result</h2>
              <p>
                These are suggestions, not verified candidate facts. Review your profile before generating a
                document.
              </p>
            </div>
            <button
              className="icon-btn"
              aria-label="Dismiss extraction result"
              onClick={() => setProposal(null)}
            >
              <X size={18} />
            </button>
          </div>
          <pre>{JSON.stringify(proposal, null, 2)}</pre>
        </section>
      )}
      <section className="panel">
        <div className="panel-head">
          <div>
            <h2>
              Document library <span className="subtle-count">{documents.length}</span>
            </h2>
            <p>Every original and generated version is kept for review.</p>
          </div>
          <LockKeyhole size={17} className="muted" />
        </div>
        {documents.length ? (
          <div className="table-scroll">
            <table className="quiet-table">
              <thead>
                <tr>
                  <th>Document</th>
                  <th>Type</th>
                  <th>Version</th>
                  <th>Created</th>
                  <th>
                    <span className="sr-only">Download</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {documents.map((d) => (
                  <tr key={d.id}>
                    <td>
                      <div className="table-document">
                        <span className="document-icon">
                          <FileText size={19} />
                        </span>
                        <span>
                          <strong>{d.filename}</strong>
                          <small>
                            {d.opportunity_id
                              ? jobs.find((j) => j.id === d.opportunity_id)?.company || 'Application document'
                              : 'Your private library'}
                          </small>
                        </span>
                      </div>
                    </td>
                    <td>{human(d.kind)}</td>
                    <td>v{d.version || 1}</td>
                    <td>{timestamp(d.created_at)}</td>
                    <td>
                      <Button variant="ghost" size="sm" asChild>
                        <a href={`/api/documents/${d.id}/download`}>
                          <ArrowDownToLine size={16} />
                          Download
                        </a>
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty icon={FileText} title="A clean slate for your story">
            Upload your original resume or generate a tailored document. Your history will appear here.
          </Empty>
        )}
      </section>
    </>
  );
}

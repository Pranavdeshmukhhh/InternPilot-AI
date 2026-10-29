'use client';
import { useState } from 'react';

import {
  ArrowRight,
  ArrowUpRight,
  BriefcaseBusiness,
  CheckCheck,
  CheckCircle2,
  ChevronRight,
  Download,
  ExternalLink,
  Plus,
  RefreshCw,
  ShieldCheck,
  UploadCloud,
} from 'lucide-react';
import { Button } from '@/components/ui/button';

import { ApplicationChecklist } from '@/components/application-checklist';

import { ApplicationBoard } from '@/components/application-board';

import { api } from '@/lib/api-client';
import type { Perform } from '@/lib/legacy-types';
import type { Application as Item } from '@/lib/api-types';
import { timestamp, url } from '@/features/shared/format';
import { Status, Empty, Modal, PageTitle } from '@/features/shared/primitives';
export function applicationOrigin(application: Item) {
  const target = url(
    application.upload_origin ||
      application.application_origin ||
      application.url ||
      application.application_url,
  );
  return target ? new URL(target).origin : undefined;
}
export function ApplicationsView({
  applications,
  busy,
  perform,
  onExplore,
  onJob,
}: {
  applications: Item[];
  busy: string;
  perform: Perform;
  onExplore: () => void;
  onJob: (id: string) => void;
}) {
  const [layout, setLayout] = useState<'board' | 'list'>('board');
  const [filter, setFilter] = useState('');
  const [uploadApproval, setUploadApproval] = useState<Item | null>(null);
  const [uploadConsent, setUploadConsent] = useState(false);
  const [approval, setApproval] = useState<Item | null>(null);
  const [consent, setConsent] = useState(false);
  const [selected, setSelected] = useState<Item | null>(null);
  const [manualStatus, setManualStatus] = useState('interview');
  const visible = applications.filter((a) =>
    !filter || filter === 'attention'
      ? !filter || ['awaiting_review', 'needs_input', 'uncertain'].includes(a.status)
      : filter === 'submitted'
        ? a.status === 'submitted'
        : ['queued', 'preparing', 'ready'].includes(a.status),
  );
  return (
    <>
      <PageTitle
        kicker="EVERY APPLICATION, ACCOUNTED FOR"
        title="Applications"
        description="Track preparation, review decisions, and confirmed submissions."
        action={
          <Button variant="outline" onClick={onExplore}>
            <Plus size={16} />
            Find an opportunity
          </Button>
        }
      />
      <div className="tabs-line">
        {[
          ['', 'All applications'],
          ['attention', 'Needs attention'],
          ['progress', 'In progress'],
          ['submitted', 'Submitted'],
        ].map(([v, label]) => (
          <button key={v} className={filter === v ? 'selected' : ''} onClick={() => setFilter(v)}>
            {label}
            {v === '' && <span>{applications.length}</span>}
          </button>
        ))}
      </div>
      <div className="inline-actions" role="group" aria-label="Application layout">
        <Button variant={layout === 'board' ? 'default' : 'outline'} onClick={() => setLayout('board')}>
          Board
        </Button>
        <Button variant={layout === 'list' ? 'default' : 'outline'} onClick={() => setLayout('list')}>
          List
        </Button>
      </div>
      {layout === 'board' && visible.length > 0 && (
        <ApplicationBoard
          applications={visible}
          onSelect={(application) => {
            if (application.status === 'awaiting_review' && application.submission_supported) {
              setConsent(false);
              setApproval(application);
            } else if (application.upload_supported) {
              setUploadConsent(false);
              setUploadApproval(application);
            } else setSelected(application);
          }}
        />
      )}
      {(layout === 'list' || !visible.length) && (
        <section className="panel">
          {visible.length ? (
            <div className="application-list">
              {visible.map((a) => (
                <div className="application-row" key={a.id}>
                  <span className="company-mark">{(a.company || 'A').slice(0, 2)}</span>
                  <div className="application-main">
                    <button onClick={() => onJob(a.opportunity_id)}>
                      {a.title || a.opportunity_title || 'Internship application'}
                      <ArrowUpRight size={13} />
                    </button>
                    <span>
                      {a.is_demo && <span className="test-tag">LOCAL TEST</span>}{' '}
                      {a.company || 'Company not recorded'} · Started {timestamp(a.created_at)}
                    </span>
                    {a.reason && <p>{a.reason}</p>}
                    {a.confirmation_id && (
                      <small className="confirmation">
                        <CheckCheck size={13} />
                        Confirmation: {a.confirmation_id}
                      </small>
                    )}
                  </div>
                  <div className="application-controls">
                    <Status value={a.status} />
                    <div>
                      {a.upload_supported && !a.submission_supported && (
                        <Button
                          size="sm"
                          onClick={() => {
                            setUploadConsent(false);
                            setUploadApproval(a);
                          }}
                          disabled={!!busy}
                        >
                          Review resume upload
                          <ArrowRight size={14} />
                        </Button>
                      )}
                      {a.status === 'awaiting_review' && a.submission_supported && (
                        <Button
                          size="sm"
                          onClick={() => {
                            setConsent(false);
                            setApproval(a);
                          }}
                          disabled={!!busy}
                        >
                          Review submission
                          <ArrowRight size={14} />
                        </Button>
                      )}
                      {['failed', 'needs_input', 'awaiting_review'].includes(a.status) &&
                        !a.upload_started_at && (
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() =>
                              perform(
                                'retry',
                                () => api(`/applications/${a.id}/retry`, 'POST', {}),
                                'Safe retry queued. The worker will recheck all policy gates.',
                              )
                            }
                            disabled={!!busy}
                          >
                            <RefreshCw size={13} />
                            Recheck
                          </Button>
                        )}
                      {!a.submission_supported && url(a.url || a.application_url) && (
                        <Button variant="outline" size="sm" asChild>
                          <a href={url(a.url || a.application_url)} target="_blank" rel="noopener noreferrer">
                            Complete on official site
                            <ExternalLink size={12} />
                          </a>
                        </Button>
                      )}
                      <Button variant="ghost" size="sm" onClick={() => setSelected(a)}>
                        Details
                        <ChevronRight size={14} />
                      </Button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <Empty
              icon={BriefcaseBusiness}
              title={
                applications.length ? 'No applications in this view' : 'Your application journey starts here'
              }
              action={
                <Button variant="outline" onClick={onExplore}>
                  Explore opportunities
                  <ArrowRight size={15} />
                </Button>
              }
            >
              {applications.length
                ? 'Choose another status to see more of your application history.'
                : 'Choose a relevant opportunity and prepare an application. You can review every uncertain answer before proceeding.'}
            </Empty>
          )}
        </section>
      )}
      <p className="footnote">
        <ShieldCheck size={14} />A submission is recorded only after confirmation. Uncertain outcomes require
        reconciliation before any retry.
      </p>
      <Modal
        open={!!approval}
        onClose={() => setApproval(null)}
        title="Review final submission"
        eyebrow={approval?.company}
      >
        {approval && (
          <>
            <div className="callout">
              <ShieldCheck size={20} />
              <div>
                <strong>{approval.title || 'Internship application'}</strong>
                <p>
                  Approval authorizes a single submission for this application through a supported, permitted
                  adapter. The worker will recheck your profile, eligibility, limits, and emergency stop
                  immediately before submitting.
                </p>
              </div>
            </div>
            {approval.reason && <p className="mt-4">{approval.reason}</p>}
            <div className="detail-actions">
              {approval.document_id && (
                <Button variant="outline" asChild>
                  <a
                    href={`/api/documents/${approval.document_id}/download`}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    <Download size={14} />
                    Review prepared resume
                  </a>
                </Button>
              )}
              {approval.screenshot_id && (
                <Button variant="outline" asChild>
                  <a
                    href={`/api/documents/${approval.screenshot_id}/download`}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    <Download size={14} />
                    Pre-submit screenshot
                  </a>
                </Button>
              )}
            </div>
            <label className="consent-box">
              <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
              <span>
                I reviewed the prepared materials and authorize this application to be submitted once. I
                understand unsupported or sensitive questions will still pause the worker.
              </span>
            </label>
            <Button
              disabled={!consent || !!busy}
              className="w-full"
              onClick={async () => {
                const r = await perform(
                  'approve',
                  () => api(`/applications/${approval.id}/approve`, 'POST', { consent: true }),
                  'Approval recorded. The worker will revalidate before submission.',
                );
                if (r) setApproval(null);
              }}
            >
              <ShieldCheck size={16} />
              Approve this submission
            </Button>
          </>
        )}
      </Modal>
      <Modal
        open={!!uploadApproval}
        onClose={() => setUploadApproval(null)}
        title="Review resume upload"
        eyebrow={uploadApproval?.company}
      >
        {uploadApproval && (
          <>
            <div className="callout">
              <UploadCloud size={20} />
              <div>
                <strong>{uploadApproval.title || 'Application resume'}</strong>
                <p>
                  Review the exact PDF and destination before approving this upload. Approval applies only to
                  this application. You complete the final external submission yourself.
                </p>
              </div>
            </div>
            <div className="detail-facts">
              <div>
                <span>Company or organizer</span>
                <strong>{uploadApproval.company}</strong>
              </div>
              <div>
                <span>Destination origin</span>
                <strong className="mono">
                  {applicationOrigin(uploadApproval) || 'Destination unavailable'}
                </strong>
              </div>
              <div>
                <span>Application</span>
                <strong>{uploadApproval.title}</strong>
              </div>
            </div>
            <div className="detail-actions">
              {uploadApproval.document_id && (
                <Button variant="outline" asChild>
                  <a
                    href={`/api/documents/${uploadApproval.document_id}/download`}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    <Download size={14} />
                    Review resume PDF
                  </a>
                </Button>
              )}
              {url(uploadApproval.url || uploadApproval.application_url) && (
                <Button variant="outline" asChild>
                  <a
                    href={url(uploadApproval.url || uploadApproval.application_url)}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    Review official application
                    <ExternalLink size={14} />
                  </a>
                </Button>
              )}
            </div>
            <label className="consent-box">
              <input
                type="checkbox"
                checked={uploadConsent}
                onChange={(event) => setUploadConsent(event.target.checked)}
              />
              <span>
                I approve uploading this resume to{' '}
                <strong className="inline-emphasis">{uploadApproval.company}</strong> at{' '}
                <strong className="inline-emphasis">
                  {applicationOrigin(uploadApproval) || 'an unavailable destination'}
                </strong>
                .
              </span>
            </label>
            <Button
              className="w-full"
              disabled={
                !uploadConsent || !!busy || !uploadApproval.document_id || !applicationOrigin(uploadApproval)
              }
              onClick={async () => {
                const result = await perform(
                  'approve-upload',
                  () => api(`/applications/${uploadApproval.id}/approve-upload`, 'POST', { consent: true }),
                  'Upload approval recorded for this application. Final submission stays under your control.',
                );
                if (result) setUploadApproval(null);
              }}
            >
              <UploadCloud size={16} />
              Approve this upload
            </Button>
          </>
        )}
      </Modal>
      <Modal
        open={!!selected}
        onClose={() => setSelected(null)}
        title="Application record"
        eyebrow={selected?.company}
      >
        {selected && (
          <>
            <h3>{selected.title}</h3>
            <div className="mt-4">
              <Status value={selected.status} />
            </div>
            <div className="detail-facts">
              <div>
                <span>Created</span>
                <strong>{timestamp(selected.created_at)}</strong>
              </div>
              <div>
                <span>Updated</span>
                <strong>{timestamp(selected.updated_at)}</strong>
              </div>
              <div>
                <span>Confirmation ID</span>
                <strong>{selected.confirmation_id || 'No confirmed submission'}</strong>
              </div>
              <div>
                <span>Application ID</span>
                <strong className="mono">{selected.id}</strong>
              </div>
            </div>
            <p className="job-description">{selected.reason || 'No additional worker notes.'}</p>
            {selected.confirmation_text && (
              <div className="callout">
                <CheckCircle2 size={18} />
                <p>{selected.confirmation_text}</p>
              </div>
            )}
            <div className="detail-actions">
              {selected.document_id && (
                <Button variant="outline" asChild>
                  <a href={`/api/documents/${selected.document_id}/download`}>
                    <Download size={14} />
                    Resume
                  </a>
                </Button>
              )}
              {selected.screenshot_id && (
                <Button variant="outline" asChild>
                  <a href={`/api/documents/${selected.screenshot_id}/download`}>
                    <Download size={14} />
                    Screenshot
                  </a>
                </Button>
              )}
            </div>
            <ApplicationChecklist applicationId={selected.id} api={api} />
            <div className="detail-section">
              <h3>Record a status update</h3>
              <p className="muted">
                Updates entered here are labeled as manually reported. They do not create a submission
                confirmation.
              </p>
              <div className="inline-form">
                <select
                  aria-label="Reported application status"
                  value={manualStatus}
                  onChange={(e) => setManualStatus(e.target.value)}
                >
                  <option value="interview">Interview</option>
                  <option value="assessment">Assessment</option>
                  <option value="rejected">Rejected</option>
                  <option value="offer">Offer</option>
                  <option value="withdrawn">Withdrawn</option>
                </select>
                <Button
                  variant="outline"
                  disabled={!!busy}
                  onClick={async () => {
                    const r = await perform(
                      'status',
                      () => api<Item>(`/applications/${selected.id}`, 'PATCH', { status: manualStatus }),
                      'Manually reported status recorded.',
                    );
                    if (r) setSelected(r);
                  }}
                >
                  Save update
                </Button>
              </div>
            </div>
          </>
        )}
      </Modal>
    </>
  );
}

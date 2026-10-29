'use client';

import type { Application } from '@/lib/api-types';
import { applicationStage } from '@/lib/application-status';
const columns = [
  { label: 'Preparing', statuses: ['queued', 'preparing', 'ready', 'approved'] },
  { label: 'Review', statuses: ['awaiting_review', 'needs_input', 'uncertain', 'failed'] },
  { label: 'Follow-up', statuses: ['submitted', 'assessment', 'interview'] },
  { label: 'Closed', statuses: ['offer', 'rejected', 'withdrawn'] },
];

export function ApplicationBoard({
  applications,
  onSelect,
}: {
  applications: Application[];
  onSelect: (application: Application) => void;
}) {
  return (
    <div className="kanban" aria-label="Application board">
      {columns.map((column) => {
        const rows = applications.filter(
          (application) => applicationStage(application.status) === column.label,
        );
        return (
          <section className="kanban-column" key={column.label} aria-label={column.label}>
            <h2 className="kanban-heading">
              {column.label}
              <span>{rows.length}</span>
            </h2>
            {rows.length ? (
              rows.map((application) => (
                <button className="kanban-entry" key={application.id} onClick={() => onSelect(application)}>
                  <small>
                    {application.company}{' '}
                    {application.is_demo && <span className="test-tag">LOCAL TEST</span>}
                  </small>
                  <strong>{application.title}</strong>
                  <p>{application.status.replaceAll('_', ' ')}</p>
                  {application.confirmation_id && <small>Confirmation: {application.confirmation_id}</small>}
                  {!application.confirmation_id &&
                    ['assessment', 'interview', 'offer', 'rejected', 'withdrawn'].includes(
                      application.status,
                    ) && <small>Manually reported</small>}
                </button>
              ))
            ) : (
              <p className="kanban-empty">No applications here</p>
            )}
          </section>
        );
      })}
    </div>
  );
}

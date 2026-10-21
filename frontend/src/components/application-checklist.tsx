'use client';

import { useEffect, useState } from 'react';
import { CheckCircle2, CircleHelp, Clock3 } from 'lucide-react';

type Stage = { id: string; label: string; state: string; detail: string };
type Props = { applicationId: string; api: (path: string) => Promise<{ stages: Stage[] }> };

export function ApplicationChecklist({ applicationId, api }: Props) {
  const [stages, setStages] = useState<Stage[]>([]);
  const [error, setError] = useState('');
  useEffect(() => {
    let current = true;
    api(`/applications/${applicationId}/checklist`).then(result => { if (current) setStages(result.stages); }).catch(reason => { if (current) setError(reason.message); });
    return () => { current = false; };
  }, [applicationId, api]);
  return <section className="detail-section"><h3>Application readiness</h3>{error && <p role="alert">{error}</p>}{stages.length ? <ul className="reason-list">{stages.map(stage => <li key={stage.id}>{['ready', 'confirmed'].includes(stage.state) ? <CheckCircle2 size={16} /> : ['needs_input', 'blocked', 'uncertain'].includes(stage.state) ? <CircleHelp size={16} /> : <Clock3 size={16} />}<div><strong>{stage.label}</strong><p className="muted">{stage.detail}</p></div></li>)}</ul> : !error && <p className="muted">Checking the saved application state…</p>}</section>;
}

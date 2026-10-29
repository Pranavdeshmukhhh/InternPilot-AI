import type { components } from './generated-api-types';

// Requests generated from FastAPI. Unmodelled response DTOs are explicit here;
// backend response-model coverage is a separate migration, not invented schemas.
export type Policy = Required<components['schemas']['Policy']>;
export type Project = { name: string; description: string; skills: string[] };
export type Experience = { title: string; organization: string; description: string };
export type Profile = Omit<Required<components['schemas']['Profile']>, 'projects' | 'experience'> & {
  projects: Project[];
  experience: Experience[];
};
export interface Session {
  csrf_token: string;
  user: { id: string; email: string; role: 'owner' | 'member' };
}
export interface Health {
  status: string;
  allow_registration: boolean;
  registration_requires_invite: boolean;
  invitation_only: boolean;
  test_mode: boolean;
}
export interface MatchEvaluation {
  score?: number;
  eligibility?: 'eligible' | 'review' | 'ineligible';
  reasons?: string[];
  verified?: string[];
  inferred?: string[];
  skill_overlap?: string[];
  missing_skills?: string[];
  recommended_action?: string;
  deadline_urgency?: string;
}
export interface Opportunity extends MatchEvaluation {
  id: string;
  title: string;
  company: string;
  url?: string;
  description?: string;
  location?: string;
  remote?: boolean;
  opportunity_type?: 'internship' | 'hackathon';
  compensation?: string | null;
  deadline?: string | null;
  published_at?: string | null;
  first_discovered_at?: string;
  last_verified_at?: string;
  source_kind?: string;
  first_discovered?: string;
  last_verified?: string;
  source?: string;
  verification_status?: string;
  verification_note?: string;
  verification_evidence_url?: string;
  active?: boolean;
  status?: string;
  saved?: boolean;
  is_demo?: boolean;
  skills?: string[];
  evaluation?: MatchEvaluation;
  match_evaluation?: MatchEvaluation;
  application_status?: string | null;
  requirements?: Record<string, unknown>;
  llm_analysis?: Record<string, unknown>;
}
export interface OpportunityPage {
  items: Opportunity[];
  total?: number;
  page?: number;
  has_more?: boolean;
  next_cursor?: string | null;
  as_of?: string;
}
export interface Application {
  id: string;
  opportunity_id: string;
  status: string;
  title: string;
  company: string;
  created_at: string;
  confirmation_id?: string | null;
  is_demo?: boolean;
  reason?: string;
  updated_at?: string;
  opportunity_title?: string;
  application_url?: string;
  application_origin?: string;
  upload_origin?: string;
  document_id?: string | null;
  screenshot_id?: string | null;
  upload_started_at?: string | null;
  confirmation_text?: string | null;
  submission_supported?: boolean;
  upload_supported?: boolean;
  url?: string;
}
export interface Document {
  id: string;
  kind: string;
  version: number;
  created_at: string;
  opportunity_id?: string | null;
  filename?: string;
}
export interface Source {
  id: string;
  company: string;
  kind: string;
  enabled: boolean;
  permitted: boolean;
  status: string;
  error?: string;
  last_success?: string;
  next_run?: string;
  failures?: number;
}
export interface AuditEvent {
  id: string;
  kind: string;
  message: string;
  created_at: string;
  application_id?: string | null;
}
export interface Task {
  id: string;
  kind: string;
  status: string;
  attempts: number;
  error?: string;
  created_at: string;
  updated_at: string;
  lease_until?: string;
}
export interface Notification {
  id: string;
  kind: string;
  message: string;
  read: boolean;
  read_at?: string;
  created_at: string;
  opportunity_id?: string;
}
export interface WorkerStatus {
  status?: string;
  active_workers?: number;
  capacity?: number;
  queued?: number;
  running?: number;
  failed?: number;
  last_seen?: string;
  control?: { paused: boolean; paused_kinds?: string[] };
}
export interface Dashboard {
  metrics: Record<string, number>;
  recent_events: AuditEvent[];
  source_health: Source[];
  worker: WorkerStatus;
}

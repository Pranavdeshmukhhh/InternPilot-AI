'use client';
import { useState, useEffect } from 'react';

import {
  BookOpen,
  BriefcaseBusiness,
  Check,
  ExternalLink,
  GraduationCap,
  LoaderCircle,
  LockKeyhole,
  Plus,
  Settings2,
  ShieldCheck,
  Trash2,
  UserRound,
} from 'lucide-react';
import { Button } from '@/components/ui/button';

import type { Profile, Project, Experience } from '@/lib/api-types';
type ScalarProfileKey =
  | 'name'
  | 'email'
  | 'phone'
  | 'country'
  | 'degree'
  | 'university'
  | 'graduation_year'
  | 'github'
  | 'linkedin'
  | 'portfolio'
  | 'availability_start'
  | 'availability_end';

import { Field, PageTitle } from '@/features/shared/primitives';
export function ProfileView({
  initial,
  onSave,
  busy,
}: {
  initial: Profile;
  onSave: (p: Profile) => Promise<void>;
  busy: boolean;
}) {
  const [p, setP] = useState<Profile>(initial);
  const [projects, setProjects] = useState<Project[]>(initial.projects || []);
  const [experience, setExperience] = useState<Experience[]>(initial.experience || []);
  useEffect(() => {
    setP(initial);
    setProjects(initial.projects || []);
    setExperience(initial.experience || []);
  }, [initial]);
  const set = <K extends keyof Profile>(k: K, v: Profile[K]) =>
    setP((o) => ({
      ...o,
      [k]: v,
      verified_fields: (o.verified_fields || []).filter((f: string) => f !== k),
    }));
  const verified = (k: keyof Profile, enabled: boolean) =>
    setP((o) => ({
      ...o,
      verified_fields: enabled
        ? [...new Set([...(o.verified_fields || []), k])]
        : (o.verified_fields || []).filter((f: string) => f !== k),
    }));
  const textField = (k: ScalarProfileKey, label: string, type = 'text', placeholder = '', hint?: string) => (
    <div className="verified-field" key={k}>
      <Field label={label} hint={hint}>
        <input
          type={type}
          value={k === 'graduation_year' && !Number.isFinite(p.graduation_year) ? '' : (p[k] ?? '')}
          onChange={(e) =>
            k === 'graduation_year'
              ? set(k, e.target.value ? Number(e.target.value) : Number.NaN)
              : set(k, e.target.value)
          }
          placeholder={placeholder}
          {...(type === 'number' ? { min: 2020, max: 2050, required: true } : {})}
        />
      </Field>
      <label className="verify-check">
        <input
          type="checkbox"
          checked={(p.verified_fields || []).includes(k)}
          disabled={!p[k]}
          onChange={(e) => verified(k, e.target.checked)}
        />
        <span>
          <ShieldCheck size={12} />I verify this is accurate
        </span>
      </label>
    </div>
  );
  const addProject = () => {
    setProjects([...projects, { name: '', description: '', skills: [] }]);
    verified('projects', false);
  };
  const addExperience = () => {
    setExperience([...experience, { title: '', organization: '', description: '' }]);
    verified('experience', false);
  };
  return (
    <>
      <PageTitle
        kicker="THE FACTS BEHIND YOUR APPLICATIONS"
        title="Candidate profile"
        description="Keep your qualifications accurate, current, and explicitly verified."
      />
      <div className="callout profile-callout">
        <ShieldCheck size={21} />
        <div>
          <strong>Verified facts are the only facts we use.</strong>
          <p>
            Check the verification box after reviewing each field. Editing a fact clears its verification.
            Imported resume suggestions are never automatically approved.
          </p>
        </div>
      </div>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          onSave({
            ...p,
            skills: (p.skills || []).filter(Boolean),
            interests: (p.interests || []).filter(Boolean),
            work_authorization: (p.work_authorization || []).filter(Boolean),
            preferred_employers: (p.preferred_employers || []).filter(Boolean),
            preferred_locations: (p.preferred_locations || []).filter(Boolean),
            projects: projects.map((x) => ({ ...x, skills: (x.skills || []).filter(Boolean) })),
            experience,
          });
        }}
      >
        <section className="panel form-section">
          <div className="form-section-intro">
            <span className="form-section-icon">
              <UserRound size={20} />
            </span>
            <h2>Personal details</h2>
            <p>Contact information for application forms and generated documents.</p>
          </div>
          <div className="form-grid">
            {textField('name', 'Full name', 'text', 'Your name as it should appear')}
            {textField('email', 'Application email', 'email', 'you@example.com')}
            {textField('phone', 'Phone number', 'tel', '+91 …')}
            {textField('country', 'Country of residence', 'text', 'India')}
          </div>
        </section>
        <section className="panel form-section">
          <div className="form-section-intro">
            <span className="form-section-icon">
              <GraduationCap size={21} />
            </span>
            <h2>Education</h2>
            <p>Explicit graduation eligibility matters. We never guess your grades or enrollment details.</p>
          </div>
          <div className="form-grid">
            {textField('university', 'University / institution', 'text', 'Institution name')}
            {textField('degree', 'Degree / program', 'text', 'e.g. B.Tech Computer Science')}
            {textField('graduation_year', 'Expected graduation year', 'number')}
            <div className="verified-field">
              <Field
                label="Countries with verified work authorization"
                hint="Separate countries with commas. This does not answer legal or sponsorship questions automatically."
              >
                <input
                  value={(p.work_authorization || []).join(', ')}
                  onChange={(e) =>
                    set(
                      'work_authorization',
                      e.target.value.split(',').map((x) => x.trim()),
                    )
                  }
                  placeholder="Only countries where you are authorized"
                />
              </Field>
              <label className="verify-check">
                <input
                  type="checkbox"
                  checked={(p.verified_fields || []).includes('work_authorization')}
                  onChange={(e) => verified('work_authorization', e.target.checked)}
                />
                <span>
                  <ShieldCheck size={12} />I verify this is accurate
                </span>
              </label>
            </div>
          </div>
        </section>
        <section className="panel form-section">
          <div className="form-section-intro">
            <span className="form-section-icon">
              <BookOpen size={20} />
            </span>
            <h2>Skills & interests</h2>
            <p>List skills you can substantiate. Interests guide discovery and do not claim experience.</p>
          </div>
          <div className="form-grid">
            <div className="verified-field">
              <Field label="Verified technical skills" hint="Separate skills with commas.">
                <textarea
                  rows={3}
                  value={Array.isArray(p.skills) ? p.skills.join(', ') : p.skills || ''}
                  onChange={(e) =>
                    set(
                      'skills',
                      e.target.value.split(',').map((x) => x.trim()),
                    )
                  }
                  placeholder="Python, JavaScript, Git…"
                />
              </Field>
              <label className="verify-check">
                <input
                  type="checkbox"
                  disabled={!p.skills?.length}
                  checked={(p.verified_fields || []).includes('skills')}
                  onChange={(e) => verified('skills', e.target.checked)}
                />
                <span>
                  <ShieldCheck size={12} />I can substantiate these skills
                </span>
              </label>
            </div>
            <Field label="Areas of interest" hint="Separate areas with commas.">
              <textarea
                rows={3}
                value={Array.isArray(p.interests) ? p.interests.join(', ') : p.interests || ''}
                onChange={(e) =>
                  set(
                    'interests',
                    e.target.value.split(',').map((x) => x.trim()),
                  )
                }
                placeholder="Software engineering, AI/ML, cloud computing…"
              />
            </Field>
          </div>
        </section>
        <section className="panel form-section">
          <div className="form-section-intro">
            <span className="form-section-icon">
              <Settings2 size={20} />
            </span>
            <h2>Search preferences</h2>
            <p>Guide ranking with your preferred employers, locations, and working arrangements.</p>
          </div>
          <div className="form-grid">
            <Field label="Preferred roles" hint="Separate role names with commas.">
              <textarea
                rows={2}
                value={(p.preferred_roles || []).join(', ')}
                onChange={(e) =>
                  set(
                    'preferred_roles',
                    e.target.value.split(',').map((x) => x.trim()),
                  )
                }
              />
            </Field>
            <Field label="Hackathon interests" hint="Topics guide recommendations and do not claim skills.">
              <textarea
                rows={2}
                value={(p.hackathon_interests || []).join(', ')}
                onChange={(e) =>
                  set(
                    'hackathon_interests',
                    e.target.value.split(',').map((x) => x.trim()),
                  )
                }
              />
            </Field>
            <Field label="Experience level">
              <select
                value={p.experience_level || 'beginner'}
                onChange={(e) => set('experience_level', e.target.value as Profile['experience_level'])}
              >
                <option value="beginner">Student / beginner</option>
                <option value="intermediate">Intermediate</option>
                <option value="advanced">Advanced</option>
              </select>
            </Field>
            {textField('availability_start', 'Available from', 'date')}
            {textField('availability_end', 'Available until', 'date')}
            <Field label="Preferred employers" hint="Separate company names with commas.">
              <textarea
                rows={3}
                value={(p.preferred_employers || []).join(', ')}
                onChange={(e) =>
                  set(
                    'preferred_employers',
                    e.target.value.split(',').map((x) => x.trim()),
                  )
                }
              />
            </Field>
            <Field label="Preferred locations" hint="Separate locations with commas.">
              <textarea
                rows={3}
                value={(p.preferred_locations || []).join(', ')}
                onChange={(e) =>
                  set(
                    'preferred_locations',
                    e.target.value.split(',').map((x) => x.trim()),
                  )
                }
              />
            </Field>
            <label className="check-label">
              <input
                type="checkbox"
                checked={!!p.remote_preferred}
                onChange={(e) => set('remote_preferred', e.target.checked)}
              />
              Prefer remote opportunities
            </label>
            <label className="check-label">
              <input
                type="checkbox"
                checked={!!p.paid_preferred}
                onChange={(e) => set('paid_preferred', e.target.checked)}
              />
              Prefer paid opportunities
            </label>
          </div>
        </section>
        <section className="panel form-section">
          <div className="form-section-intro">
            <span className="form-section-icon">
              <ExternalLink size={20} />
            </span>
            <h2>Your work online</h2>
            <p>Provide public links you want included in relevant applications.</p>
          </div>
          <div className="form-grid">
            {textField('github', 'GitHub', 'url', 'https://github.com/…')}
            {textField('linkedin', 'LinkedIn', 'url', 'https://linkedin.com/in/…')}
            {textField('portfolio', 'Portfolio website', 'url', 'https://…')}
          </div>
        </section>
        <section className="panel form-section">
          <div className="form-section-intro">
            <span className="form-section-icon">
              <BookOpen size={20} />
            </span>
            <h2>Projects</h2>
            <p>
              Real projects and outcomes from your coursework, independent work, or open-source contributions.
            </p>
            <Button variant="outline" size="sm" type="button" onClick={addProject}>
              <Plus size={14} />
              Add project
            </Button>
          </div>
          <div className="repeated-fields">
            {projects.length ? (
              projects.map((project, i) => (
                <div className="repeated-item" key={i}>
                  <div className="repeated-item-head">
                    <strong>Project {i + 1}</strong>
                    <button
                      type="button"
                      className="icon-btn"
                      aria-label={`Remove project ${i + 1}`}
                      onClick={() => {
                        setProjects(projects.filter((_, n) => n !== i));
                        verified('projects', false);
                      }}
                    >
                      <Trash2 size={15} />
                    </button>
                  </div>
                  <Field label="Project name">
                    <input
                      value={project.name}
                      onChange={(e) => {
                        setProjects(projects.map((x, n) => (n === i ? { ...x, name: e.target.value } : x)));
                        verified('projects', false);
                      }}
                    />
                  </Field>
                  <Field label="What you built and achieved">
                    <textarea
                      rows={3}
                      value={project.description}
                      onChange={(e) => {
                        setProjects(
                          projects.map((x, n) => (n === i ? { ...x, description: e.target.value } : x)),
                        );
                        verified('projects', false);
                      }}
                    />
                  </Field>
                  <Field label="Skills used">
                    <input
                      value={(project.skills || []).join(', ')}
                      onChange={(e) => {
                        setProjects(
                          projects.map((x, n) =>
                            n === i ? { ...x, skills: e.target.value.split(',').map((s) => s.trim()) } : x,
                          ),
                        );
                        verified('projects', false);
                      }}
                    />
                  </Field>
                </div>
              ))
            ) : (
              <p className="inline-empty">
                No projects added yet. Add only work you have completed or clearly describe work in progress.
              </p>
            )}
            <label className="verify-check">
              <input
                type="checkbox"
                disabled={!projects.length}
                checked={(p.verified_fields || []).includes('projects')}
                onChange={(e) => verified('projects', e.target.checked)}
              />
              <span>
                <ShieldCheck size={12} />I verify all project descriptions are accurate
              </span>
            </label>
          </div>
        </section>
        <section className="panel form-section">
          <div className="form-section-intro">
            <span className="form-section-icon">
              <BriefcaseBusiness size={20} />
            </span>
            <h2>Experience</h2>
            <p>Optional. Beginner applicants do not need invented work experience.</p>
            <Button variant="outline" size="sm" type="button" onClick={addExperience}>
              <Plus size={14} />
              Add experience
            </Button>
          </div>
          <div className="repeated-fields">
            <div className="verified-field">
              <Field
                label="Total relevant professional experience (years)"
                hint="Use 0 if accurate. Leave blank if you have not verified this."
              >
                <input
                  type="number"
                  min={0}
                  max={80}
                  step={0.5}
                  value={p.experience_years ?? ''}
                  onChange={(e) =>
                    set('experience_years', e.target.value === '' ? null : Number(e.target.value))
                  }
                />
              </Field>
              <label className="verify-check">
                <input
                  type="checkbox"
                  disabled={p.experience_years == null}
                  checked={(p.verified_fields || []).includes('experience_years')}
                  onChange={(e) => verified('experience_years', e.target.checked)}
                />
                <span>
                  <ShieldCheck size={12} />I verify this experience duration is accurate
                </span>
              </label>
            </div>
            {experience.length ? (
              experience.map((exp, i) => (
                <div className="repeated-item" key={i}>
                  <div className="repeated-item-head">
                    <strong>Experience {i + 1}</strong>
                    <button
                      type="button"
                      className="icon-btn"
                      aria-label={`Remove experience ${i + 1}`}
                      onClick={() => {
                        setExperience(experience.filter((_, n) => n !== i));
                        verified('experience', false);
                      }}
                    >
                      <Trash2 size={15} />
                    </button>
                  </div>
                  <div className="form-grid">
                    <Field label="Role / title">
                      <input
                        value={exp.title}
                        onChange={(e) => {
                          setExperience(
                            experience.map((x, n) => (n === i ? { ...x, title: e.target.value } : x)),
                          );
                          verified('experience', false);
                        }}
                      />
                    </Field>
                    <Field label="Organization">
                      <input
                        value={exp.organization}
                        onChange={(e) => {
                          setExperience(
                            experience.map((x, n) => (n === i ? { ...x, organization: e.target.value } : x)),
                          );
                          verified('experience', false);
                        }}
                      />
                    </Field>
                  </div>
                  <Field label="Responsibilities and outcomes">
                    <textarea
                      rows={3}
                      value={exp.description}
                      onChange={(e) => {
                        setExperience(
                          experience.map((x, n) => (n === i ? { ...x, description: e.target.value } : x)),
                        );
                        verified('experience', false);
                      }}
                    />
                  </Field>
                </div>
              ))
            ) : (
              <p className="inline-empty">
                No experience added. Your projects, education, and verified skills can tell your story.
              </p>
            )}
            <label className="verify-check">
              <input
                type="checkbox"
                disabled={!experience.length}
                checked={(p.verified_fields || []).includes('experience')}
                onChange={(e) => verified('experience', e.target.checked)}
              />
              <span>
                <ShieldCheck size={12} />I verify all experience is accurate
              </span>
            </label>
          </div>
        </section>
        <div className="save-bar">
          <span>
            <LockKeyhole size={14} />
            Stored encrypted in your private workspace.
          </span>
          <Button type="submit" disabled={busy}>
            {busy ? <LoaderCircle size={16} className="spin" /> : <Check size={16} />}Save verified profile
          </Button>
        </div>
      </form>
    </>
  );
}

'use client';

import { useEffect, useState, type ReactNode } from 'react';
import { ArrowLeft, ArrowRight, Bookmark, Compass, Filter, LoaderCircle, RefreshCw, Search, Sparkles, Trophy, X } from 'lucide-react';
import { Button } from '@/components/ui/button';

type Item = Record<string, any>;
type Mode = 'internship' | 'hackathon' | 'recommended' | 'saved';
type Props = {
  mode: Mode;
  api: (path: string, method?: string, body?: unknown) => Promise<any>;
  busy: boolean;
  stopped: boolean;
  refreshKey: number;
  onDiscover: () => void;
  renderJob: (job: Item) => ReactNode;
};
const descriptions = {
  internship: { kicker: 'TURN POTENTIAL INTO EXPERIENCE', title: 'Internships, with context.', description: 'Find real roles with clear requirements, verified eligibility, and a next step.', icon: Compass },
  hackathon: { kicker: 'BUILD SOMETHING THAT MATTERS', title: 'Your next challenge awaits.', description: 'Explore hackathons, check participation requirements, and keep registration deadlines in view.', icon: Trophy },
  recommended: { kicker: 'A MORE FOCUSED SHORTLIST', title: 'Recommended for your next move.', description: 'Matches selected from your verified profile. Every recommendation keeps eligibility and deadlines in view.', icon: Sparkles },
  saved: { kicker: 'KEEP THE POSSIBILITIES CLOSE', title: 'Your saved opportunities.', description: 'A private shortlist of internships and hackathons you want to revisit.', icon: Bookmark },
};

export function OpportunityExplorer({ mode, api, busy, stopped, refreshKey, onDiscover, renderJob }: Props) {
  const copy = descriptions[mode];
  const [search, setSearch] = useState('');
  const [query, setQuery] = useState('');
  const [company, setCompany] = useState('');
  const [location, setLocation] = useState('');
  const [eligibility, setEligibility] = useState('');
  const [kind, setKind] = useState('');
  const [deadline, setDeadline] = useState('');
  const [remote, setRemote] = useState(false);
  const [paid, setPaid] = useState(false);
  const [includeClosed, setIncludeClosed] = useState(false);
  const [sort, setSort] = useState('score');
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [page, setPage] = useState(1);
  const [items, setItems] = useState<Item[]>([]);
  const [total, setTotal] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  const pageSize = 20;
  const hasFilters = !!(query || company || location || eligibility || kind || deadline || remote || paid || includeClosed);

  useEffect(() => { const timer = setTimeout(() => { setQuery(search.trim()); setPage(1); }, 300); return () => clearTimeout(timer); }, [search]);
  useEffect(() => {
    let current = true;
    const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
    if (mode === 'internship' || mode === 'hackathon') params.set('kind', mode);
    else { params.set(mode, 'true'); if (kind) params.set('kind', kind); }
    if (query) params.set('search', query);
    if (company.trim()) params.set('company', company.trim());
    if (location.trim()) params.set('location', location.trim());
    if (eligibility) params.set('eligibility', eligibility);
    if (deadline) params.set('deadline_before', deadline);
    params.set('sort', sort);
    if (includeClosed) params.set('include_closed', 'true');
    if (remote) params.set('remote', 'true');
    if (paid) params.set('paid', 'true');
    setLoading(true); setError('');
    api(`/opportunities/page?${params}`).then(result => {
      if (!current) return;
      const count = typeof result.total === 'number' ? result.total : 0;
      if (page > 1 && count <= (page - 1) * pageSize) { setPage(Math.max(1, Math.ceil(count / pageSize))); return; }
      setItems(Array.isArray(result.items) ? result.items : []); setTotal(count);
    }).catch(reason => { if (current) setError(reason.message); }).finally(() => { if (current) setLoading(false); });
    return () => { current = false; };
  }, [api, mode, query, company, location, eligibility, kind, deadline, remote, paid, includeClosed, sort, page, refreshKey, retry]);
  const changeFilter = (apply: () => void) => { apply(); setPage(1); };
  const reset = () => { setSearch(''); setQuery(''); setCompany(''); setLocation(''); setEligibility(''); setKind(''); setDeadline(''); setRemote(false); setPaid(false); setIncludeClosed(false); setPage(1); };
  const pages = Math.max(1, Math.ceil((total || 0) / pageSize));

  return <>
    <div className="page-title-row"><div><div className="section-kicker">{copy.kicker}</div><h1>{copy.title}</h1><p className="page-subtitle">{copy.description}</p></div>{mode !== 'saved' && <Button onClick={onDiscover} disabled={busy || stopped}><RefreshCw size={16} />Find opportunities</Button>}</div>
    <div className="search-toolbar"><div className="search-input"><Search size={18} /><input aria-label="Search opportunities" placeholder="Search title, company, or skill…" value={search} onChange={event => setSearch(event.target.value)} />{search && <button className="icon-btn" aria-label="Clear search" onClick={() => setSearch('')}><X size={15} /></button>}</div><select aria-label="Eligibility filter" value={eligibility} onChange={event => changeFilter(() => setEligibility(event.target.value))}><option value="">All eligibility</option><option value="eligible">Eligible</option><option value="review">Needs review</option><option value="ineligible">Ineligible</option></select><Button variant="outline" aria-expanded={filtersOpen} onClick={() => setFiltersOpen(value => !value)}><Filter size={15} />Filters{hasFilters && <span className="filter-active" />}</Button></div>
    {filtersOpen && <div className="filter-panel">
      {(mode === 'saved' || mode === 'recommended') && <label className="field"><span className="field-label">Opportunity type</span><select value={kind} onChange={event => changeFilter(() => setKind(event.target.value))}><option value="">All opportunities</option><option value="internship">Internships</option><option value="hackathon">Hackathons</option></select></label>}
      <label className="field"><span className="field-label">Company or organizer</span><input value={company} onChange={event => changeFilter(() => setCompany(event.target.value))} placeholder="Company name" /></label>
      <label className="field"><span className="field-label">Location</span><input value={location} onChange={event => changeFilter(() => setLocation(event.target.value))} placeholder="City or country" /></label>
      <label className="field"><span className="field-label">Deadline on or before</span><input type="date" value={deadline} onChange={event => changeFilter(() => setDeadline(event.target.value))} /></label>
      <label className="check-label"><input type="checkbox" checked={remote} onChange={event => changeFilter(() => setRemote(event.target.checked))} />Remote opportunities</label>
      <label className="check-label"><input type="checkbox" checked={paid} onChange={event => changeFilter(() => setPaid(event.target.checked))} />Paid internships / disclosed cash prizes</label>
      <label className="check-label"><input type="checkbox" checked={includeClosed} onChange={event => changeFilter(() => setIncludeClosed(event.target.checked))} />Include closed opportunities</label><button className="text-link" onClick={reset}>Reset filters</button>
    </div>}
    <div className="results-bar"><span>{total === null ? 'Checking opportunities…' : <><strong>{total}</strong> {total === 1 ? 'opportunity' : 'opportunities'}</>}{loading && total !== null && <LoaderCircle size={13} className="spin inline-loader" />}</span><label className="sort-control">Sort by<select value={sort} onChange={event => changeFilter(() => setSort(event.target.value))}><option value="score">Best match</option><option value="newest">Newest first</option><option value="deadline">Closing soon</option></select></label></div>
    {error && <div className="banner danger" role="alert"><span>{error}</span><button onClick={() => setRetry(value => value + 1)}>Try again</button></div>}
    <section className="panel" aria-busy={loading}>
      {loading && total === null ? <div className="explorer-loading"><LoaderCircle className="spin" size={22} /><p>Finding your opportunities…</p></div> : items.length ? <div className="opportunity-list">{items.map(renderJob)}</div> : !error && <div className="empty"><div className="empty-icon"><copy.icon size={24} strokeWidth={1.6} /></div><h3>{hasFilters ? 'No opportunities match these filters' : mode === 'saved' ? 'Make room for your next move' : mode === 'recommended' ? 'Your recommendations are taking shape' : mode === 'hackathon' ? 'Your next challenge starts here' : 'Your discovery feed is ready'}</h3><p>{hasFilters ? 'Broaden your filters to see more possibilities.' : mode === 'saved' ? 'Save an internship or hackathon using its bookmark. It will stay in this shortlist across visits.' : mode === 'recommended' ? 'Complete and verify your profile, then run discovery to find relevant opportunities.' : 'Connect a permitted source and run discovery. Real opportunities will appear here with their source and deadline.'}</p>{hasFilters ? <Button variant="outline" onClick={reset}>Reset filters</Button> : mode !== 'saved' && <Button variant="outline" onClick={onDiscover} disabled={busy || stopped}>Run discovery</Button>}</div>}
      {total !== null && total > pageSize && <div className="pagination"><span>Showing {(page - 1) * pageSize + 1}–{Math.min(page * pageSize, total)} of {total}</span><div><Button variant="outline" size="sm" disabled={loading || page <= 1} onClick={() => setPage(value => value - 1)}><ArrowLeft size={14} />Previous</Button><span>Page {page} of {pages}</span><Button variant="outline" size="sm" disabled={loading || page >= pages} onClick={() => setPage(value => value + 1)}>Next<ArrowRight size={14} /></Button></div></div>}
    </section>
    <p className="footnote"><Sparkles size={14} />Match scores explain fit. Eligibility, closing status, and your review determine the next step.</p>
  </>;
}

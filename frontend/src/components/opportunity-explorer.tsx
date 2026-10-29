'use client';

import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import {
  ArrowLeft,
  ArrowRight,
  Bookmark,
  Compass,
  Filter,
  LoaderCircle,
  RefreshCw,
  Search,
  Trophy,
  X,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import Link from 'next/link';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { Modal } from '@/features/shared/primitives';
import { useResource } from '@/features/workspace/provider';
import type { Opportunity as Item, OpportunityPage } from '@/lib/api-types';

type Mode = 'internship' | 'hackathon' | 'recommended' | 'saved';
type Props = {
  mode: Mode;
  workspaceId: string;
  api: (
    path: string,
    method?: string,
    body?: unknown,
    binary?: boolean,
    signal?: AbortSignal,
  ) => Promise<any>;
  busy: boolean;
  stopped: boolean;
  refreshKey: number;
  onDiscover: () => void;
  onPreferencesChanged: () => Promise<void>;
  localCities: string[];
  renderJob: (job: Item) => ReactNode;
};
type ExplorerState = {
  search: string;
  company: string;
  location: string;
  region: string;
  skills: string;
  degree: string;
  graduation: string;
  duration: string;
  stipend: string;
  eligibility: string;
  kind: string;
  deadline: string;
  remote: boolean;
  paid: boolean;
  includeClosed: boolean;
  sort: string;
  filtersOpen: boolean;
  page: number;
  scrollY: number;
  cursors?: Record<number, string>;
};
const storageKey = (workspaceId: string, mode: Mode) => `internpilot-explorer-v1:${workspaceId}:${mode}`;
function readPreferences(workspaceId: string, mode: Mode): ExplorerState {
  const defaults: ExplorerState = {
    search: '',
    company: '',
    location: '',
    region: 'all',
    skills: '',
    degree: '',
    graduation: '',
    duration: '',
    stipend: '',
    eligibility: '',
    kind: '',
    deadline: '',
    remote: false,
    paid: false,
    includeClosed: false,
    sort: mode === 'recommended' ? 'score' : 'newest',
    filtersOpen: false,
    page: 1,
    scrollY: 0,
  };
  try {
    let value = JSON.parse(sessionStorage.getItem(storageKey(workspaceId, mode)) || '{}');
    const url = new URLSearchParams(window.location.search);
    if (url.has('sort'))
      value = {
        ...Object.fromEntries(url),
        cursors: value.cursors,
        degree: url.get('degree_level') || '',
        graduation: url.get('graduation_year') || '',
        duration: url.get('duration_min') || '',
        stipend: url.get('stipend_min') || '',
        deadline: url.get('deadline_before') || '',
        page: Number(url.get('page') || 1),
        remote: url.get('remote') === 'true',
        paid: url.get('paid') === 'true',
        includeClosed: url.get('include_closed') === 'true',
        search: url.get('search') || '',
      };
    if (!value || typeof value !== 'object') return defaults;
    for (const key of [
      'search',
      'company',
      'location',
      'skills',
      'graduation',
      'duration',
      'stipend',
      'deadline',
    ] as const)
      if (typeof value[key] === 'string') defaults[key] = value[key].slice(0, 500);
    for (const key of ['remote', 'paid', 'includeClosed'] as const)
      if (typeof value[key] === 'boolean') defaults[key] = value[key];
    const choices = {
      region: ['all', 'local', 'india', 'international', 'worldwide', 'unknown'],
      degree: ['', 'undergraduate', 'masters', 'phd'],
      eligibility: ['', 'eligible', 'review', 'ineligible'],
      kind: ['', 'internship', 'hackathon'],
      sort: ['score', 'newest', 'deadline'],
    };
    for (const key of Object.keys(choices) as (keyof typeof choices)[])
      if (
        choices[key].includes(value[key]) &&
        !(key === 'kind' && (mode === 'internship' || mode === 'hackathon'))
      )
        defaults[key] = value[key];
    if (value.cursors && typeof value.cursors === 'object') defaults.cursors = value.cursors;
    if (Number.isInteger(value.page) && value.page > 0 && value.page <= 100000) defaults.page = value.page;
    if (Number.isFinite(value.scrollY) && value.scrollY >= 0)
      defaults.scrollY = Math.min(value.scrollY, 100000);
  } catch {
    /* Browsing remains available when storage is disabled. */
  }
  return defaults;
}
const descriptions = {
  internship: {
    kicker: 'TURN POTENTIAL INTO EXPERIENCE',
    title: 'Internships',
    description: 'Explore roles. Make your next move.',
    icon: Compass,
  },
  hackathon: {
    kicker: 'BUILD SOMETHING THAT MATTERS',
    title: 'Hackathons',
    description: 'Find your people. Build something new.',
    icon: Trophy,
  },
  recommended: {
    kicker: 'A MORE FOCUSED SHORTLIST',
    title: 'Your matches',
    description: 'Relevance explained. Eligibility kept separate.',
    icon: Compass,
  },
  saved: {
    kicker: 'KEEP THE POSSIBILITIES CLOSE',
    title: 'Saved opportunities',
    description: 'The opportunities you want to come back to.',
    icon: Bookmark,
  },
};

export function OpportunityExplorer({
  mode,
  workspaceId,
  api,
  busy,
  stopped,
  refreshKey,
  onDiscover,
  onPreferencesChanged,
  localCities,
  renderJob,
}: Props) {
  const copy = descriptions[mode];
  const router = useRouter();
  const pathname = usePathname();
  const urlParams = useSearchParams();
  const [initial] = useState(() => readPreferences(workspaceId, mode));
  const [search, setSearch] = useState(initial.search);
  const [query, setQuery] = useState(initial.search.trim());
  const [company, setCompany] = useState(initial.company);
  const [location, setLocation] = useState(initial.location);
  const [region, setRegion] = useState(initial.region);
  const [skills, setSkills] = useState(initial.skills);
  const [degree, setDegree] = useState(initial.degree);
  const [graduation, setGraduation] = useState(initial.graduation);
  const [duration, setDuration] = useState(initial.duration);
  const [stipend, setStipend] = useState(initial.stipend);
  const [eligibility, setEligibility] = useState(initial.eligibility);
  const [kind, setKind] = useState(initial.kind);
  const [deadline, setDeadline] = useState(initial.deadline);
  const [remote, setRemote] = useState(initial.remote);
  const [paid, setPaid] = useState(initial.paid);
  const [includeClosed, setIncludeClosed] = useState(initial.includeClosed);
  const [sort, setSort] = useState(initial.sort);
  const [filtersOpen, setFiltersOpen] = useState(initial.filtersOpen);
  const [page, setPage] = useState(initial.page);
  const [cursors, setCursors] = useState<Record<number, string>>(initial.cursors || { 1: '' });
  const searchInput = useRef<HTMLInputElement>(null);
  const resultsHeading = useRef<HTMLDivElement>(null);
  const resultsPanel = useRef<HTMLElement>(null);
  const resultsHeight = useRef(0);
  const focusResults = useRef(false);
  const restoreScroll = useRef(true);
  const scrollY = useRef(initial.scrollY);
  const preferences = useRef<ExplorerState>(initial);
  const pageSize = 20;
  const hasFilters = !!(
    query ||
    company ||
    location ||
    region !== 'all' ||
    eligibility ||
    kind ||
    deadline ||
    remote ||
    paid ||
    includeClosed ||
    skills ||
    degree ||
    graduation ||
    duration ||
    stipend
  );

  useEffect(() => {
    if (search.trim() === query) return;
    const timer = setTimeout(() => {
      setQuery(search.trim());
      setPage(1);
      setCursors({ 1: '' });
    }, 300);
    return () => clearTimeout(timer);
  }, [search, query]);
  useEffect(() => {
    preferences.current = {
      search,
      company,
      location,
      region,
      skills,
      degree,
      graduation,
      duration,
      stipend,
      eligibility,
      kind,
      deadline,
      remote,
      paid,
      includeClosed,
      sort,
      filtersOpen,
      page,
      scrollY: scrollY.current,
      cursors,
    };
    try {
      sessionStorage.setItem(storageKey(workspaceId, mode), JSON.stringify(preferences.current));
    } catch {
      /* Optional tab preferences. */
    }
  }, [
    workspaceId,
    mode,
    search,
    company,
    location,
    region,
    skills,
    degree,
    graduation,
    duration,
    stipend,
    eligibility,
    kind,
    deadline,
    remote,
    paid,
    includeClosed,
    sort,
    filtersOpen,
    page,
    cursors,
  ]);
  useEffect(() => {
    const rememberScroll = () => {
      scrollY.current = window.scrollY;
    };
    const shortcut = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (event.isComposing) return;
      let shortcuts = true;
      try {
        shortcuts = localStorage.getItem('internpilot-shortcuts') !== 'off';
      } catch {}
      if (
        shortcuts &&
        event.key === '/' &&
        !event.ctrlKey &&
        !event.metaKey &&
        !event.altKey &&
        !event.defaultPrevented &&
        !target?.closest('input,textarea,select,[contenteditable="true"],[role="dialog"]') &&
        !document.querySelector('[role="dialog"]')
      ) {
        event.preventDefault();
        searchInput.current?.focus();
      }
    };
    window.addEventListener('scroll', rememberScroll, { passive: true });
    window.addEventListener('keydown', shortcut);
    return () => {
      window.removeEventListener('scroll', rememberScroll);
      window.removeEventListener('keydown', shortcut);
      try {
        sessionStorage.setItem(
          storageKey(workspaceId, mode),
          JSON.stringify({ ...preferences.current, scrollY: scrollY.current }),
        );
      } catch {
        /* Optional tab preferences. */
      }
    };
  }, [workspaceId, mode]);
  const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
  if (mode === 'internship' || mode === 'hackathon') params.set('kind', mode);
  else {
    params.set(mode, 'true');
    if (kind) params.set('kind', kind);
  }
  if (query) params.set('search', query);
  if (company.trim()) params.set('company', company.trim());
  if (location.trim()) params.set('location', location.trim());
  params.set('region', region);
  if (skills.trim()) params.set('skills', skills.trim());
  if (degree) params.set('degree_level', degree);
  if (graduation) params.set('graduation_year', graduation);
  if (duration) params.set('duration_min', duration);
  if (stipend) params.set('stipend_min', stipend);
  if (eligibility) params.set('eligibility', eligibility);
  if (deadline) params.set('deadline_before', deadline);
  params.set('sort', sort);
  if (includeClosed) params.set('include_closed', 'true');
  if (remote) params.set('remote', 'true');
  if (paid) params.set('paid', 'true');
  const cursorMode =
    sort !== 'score' &&
    region === 'all' &&
    !skills &&
    !degree &&
    !graduation &&
    !duration &&
    !stipend &&
    !eligibility &&
    !deadline &&
    !paid &&
    mode !== 'recommended';
  const numberError = [
    [graduation, 2020, 2050],
    [duration, 0, 24],
    [stipend, 0, 1000000],
  ].some(
    ([value, min, max]) =>
      value !== '' &&
      (!Number.isFinite(Number(value)) || Number(value) < Number(min) || Number(value) > Number(max)),
  )
    ? 'Check the numeric filters: graduation 2020–2050, duration 0–24 months, stipend 0–1,000,000 INR.'
    : '';
  const cursorParams = new URLSearchParams({ page_size: String(pageSize), sort });
  for (const key of ['kind', 'search', 'company', 'location', 'remote', 'include_closed', 'saved'])
    if (params.has(key)) cursorParams.set(key, params.get(key)!);
  if (cursors[page]) cursorParams.set('cursor', cursors[page]);
  const requestPath = cursorMode ? `/v2/opportunities?${cursorParams}` : `/opportunities/page?${params}`;
  const result = useResource<OpportunityPage>(
    requestPath,
    !filtersOpen && !numberError && (!cursorMode || page === 1 || !!cursors[page]),
    60_000,
    150,
  );
  const items = result.data?.items || [];
  const total = result.data?.total ?? null;
  const loading = result.isFetching || (!filtersOpen && !numberError && result.isPending);
  const error = numberError || result.error?.message || '';
  const resolvedRequest = result.data ? requestPath : '';
  useEffect(() => {
    if (cursorMode && page > 1 && !cursors[page]) setPage(1);
  }, [cursorMode, page, cursors]);
  useEffect(() => {
    if (result.data?.next_cursor)
      setCursors((values) =>
        values[page + 1] === result.data!.next_cursor
          ? values
          : { ...values, [page + 1]: result.data!.next_cursor! },
      );
    if (total !== null && page > 1 && total <= (page - 1) * pageSize)
      setPage(Math.max(1, Math.ceil(total / pageSize)));
  }, [result.data, page, total]);
  const { data: deadlineData, refetch: refreshDeadline } = result;
  useEffect(() => {
    const dates = (deadlineData?.items || [])
      .map((job) => (job.deadline ? Date.parse(job.deadline) : Number.NaN))
      .filter((date) => Number.isFinite(date) && date > Date.now());
    if (!dates.length) return;
    const due = Math.min(...dates);
    const refreshWhenDue = () => {
      if (!document.hidden && Date.now() >= due) void refreshDeadline();
    };
    let timer: ReturnType<typeof setTimeout>;
    const arm = () => {
      timer = setTimeout(
        () => {
          if (Date.now() < due) arm();
          else refreshWhenDue();
        },
        Math.min(2147483647, Math.max(0, due - Date.now() + 150)),
      );
    };
    arm();
    document.addEventListener('visibilitychange', refreshWhenDue);
    return () => {
      clearTimeout(timer);
      document.removeEventListener('visibilitychange', refreshWhenDue);
    };
  }, [deadlineData, refreshDeadline]);
  const serialized = params.toString();
  const currentUrl = useRef(urlParams);
  currentUrl.current = urlParams;
  useEffect(() => {
    if (filtersOpen) return;
    const next = new URLSearchParams(serialized);
    next.delete('page_size');
    next.delete('internship');
    next.delete('hackathon');
    const current = currentUrl.current;
    if (current.get('opportunity')) next.set('opportunity', current.get('opportunity')!);
    if (next.toString() !== current.toString()) router.replace(`${pathname}?${next}`, { scroll: false });
  }, [serialized, pathname, router, filtersOpen]);
  const resultsCurrent = resolvedRequest === requestPath && search.trim() === query;
  useLayoutEffect(() => {
    const panel = resultsPanel.current;
    if (!panel) return;
    if (error) {
      panel.style.minHeight = '';
      return;
    }
    if (!resultsCurrent) {
      if (resultsHeight.current) panel.style.minHeight = `${resultsHeight.current}px`;
      return;
    }
    panel.style.minHeight = '';
    const measure = () => {
      resultsHeight.current = panel.getBoundingClientRect().height;
    };
    measure();
    if (typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(measure);
    observer.observe(panel);
    return () => observer.disconnect();
  }, [resultsCurrent, items.length, error]);
  useEffect(() => {
    if (loading || !resultsCurrent) return;
    if (focusResults.current) {
      focusResults.current = false;
      resultsHeading.current?.focus({ preventScroll: true });
      resultsHeading.current?.scrollIntoView({ block: 'start', behavior: 'instant' });
    } else if (restoreScroll.current) {
      restoreScroll.current = false;
      window.scrollTo({ top: initial.scrollY, behavior: 'instant' });
    }
  }, [loading, resultsCurrent, initial.scrollY]);
  const changeFilter = (apply: () => void) => {
    restoreScroll.current = false;
    apply();
    setPage(1);
    setCursors({ 1: '' });
  };
  const changePage = (value: number) => {
    focusResults.current = true;
    restoreScroll.current = false;
    setPage(value);
  };
  const reset = () => {
    restoreScroll.current = false;
    setSearch('');
    setQuery('');
    setCompany('');
    setLocation('');
    setRegion('all');
    setSkills('');
    setDegree('');
    setGraduation('');
    setDuration('');
    setStipend('');
    setEligibility('');
    setKind('');
    setDeadline('');
    setRemote(false);
    setPaid(false);
    setIncludeClosed(false);
    setPage(1);
    setCursors({ 1: '' });
  };
  const draftStart = useRef<ExplorerState | null>(null);
  const openFilters = () => {
    draftStart.current = { ...preferences.current };
    setFiltersOpen(true);
  };
  const cancelFilters = () => {
    const p = draftStart.current;
    if (p) {
      setCompany(p.company);
      setLocation(p.location);
      setSkills(p.skills);
      setDegree(p.degree);
      setGraduation(p.graduation);
      setDuration(p.duration);
      setStipend(p.stipend);
      setEligibility(p.eligibility);
      setKind(p.kind);
      setDeadline(p.deadline);
      setRemote(p.remote);
      setPaid(p.paid);
      setIncludeClosed(p.includeClosed);
      setPage(p.page);
      setCursors(p.cursors || { 1: '' });
    }
    setFiltersOpen(false);
  };
  const pages = Math.max(1, Math.ceil((total || 0) / pageSize));

  return (
    <>
      <div className="page-title-row">
        <div>
          <h1>{copy.title}</h1>
          <p className="page-subtitle">{copy.description}</p>
        </div>
        {mode !== 'saved' && (
          <Button onClick={onDiscover} disabled={busy || stopped}>
            <RefreshCw size={16} />
            Find opportunities
          </Button>
        )}
      </div>
      <div className="search-toolbar">
        <div className="search-input">
          <Search size={18} />
          <input
            ref={searchInput}
            aria-label="Search opportunities"
            aria-keyshortcuts="/"
            maxLength={500}
            placeholder="Search title, company, or skill…"
            value={search}
            onChange={(event) => {
              restoreScroll.current = false;
              setSearch(event.target.value);
            }}
          />
          {search ? (
            <button className="icon-btn" aria-label="Clear search" onClick={() => setSearch('')}>
              <X size={15} />
            </button>
          ) : (
            <kbd className="search-shortcut" aria-hidden="true">
              /
            </kbd>
          )}
        </div>
        <select
          aria-label="Eligibility filter"
          value={eligibility}
          onChange={(event) => changeFilter(() => setEligibility(event.target.value))}
        >
          <option value="">All eligibility</option>
          <option value="eligible">Eligible</option>
          <option value="review">Needs review</option>
          <option value="ineligible">Ineligible</option>
        </select>
        <Button
          variant="outline"
          aria-expanded={filtersOpen}
          aria-controls="opportunity-filters"
          onClick={openFilters}
        >
          <Filter size={15} />
          Filters{hasFilters && <span className="filter-active" />}
        </Button>
      </div>
      <Modal open={filtersOpen} onClose={cancelFilters} title="Refine opportunities">
        <div className="filter-panel" id="opportunity-filters">
          {(mode === 'saved' || mode === 'recommended') && (
            <label className="field">
              <span className="field-label">Opportunity type</span>
              <select value={kind} onChange={(event) => changeFilter(() => setKind(event.target.value))}>
                <option value="">All opportunities</option>
                <option value="internship">Internships</option>
                <option value="hackathon">Hackathons</option>
              </select>
            </label>
          )}
          <label className="field">
            <span className="field-label">Company or organizer</span>
            <input
              value={company}
              onChange={(event) => changeFilter(() => setCompany(event.target.value))}
              placeholder="Company name"
            />
          </label>
          <label className="field">
            <span className="field-label">Location</span>
            <input
              value={location}
              onChange={(event) => changeFilter(() => setLocation(event.target.value))}
              placeholder="City or country"
            />
          </label>
          <label className="field">
            <span className="field-label">Deadline on or before</span>
            <input
              type="date"
              value={deadline}
              onChange={(event) => changeFilter(() => setDeadline(event.target.value))}
            />
          </label>
          <label className="field">
            <span className="field-label">Required skills (comma separated)</span>
            <input
              value={skills}
              onChange={(event) => changeFilter(() => setSkills(event.target.value))}
              placeholder="Python, SQL"
            />
          </label>
          <label className="field">
            <span className="field-label">Stated degree</span>
            <select value={degree} onChange={(event) => changeFilter(() => setDegree(event.target.value))}>
              <option value="">Any / unknown</option>
              <option value="undergraduate">Undergraduate</option>
              <option value="masters">Masters</option>
              <option value="phd">PhD</option>
            </select>
          </label>
          <label className="field">
            <span className="field-label">Explicitly accepts graduation year</span>
            <input
              type="number"
              min={2020}
              max={2050}
              placeholder="2029"
              value={graduation}
              onChange={(event) => changeFilter(() => setGraduation(event.target.value))}
            />
          </label>
          <label className="field">
            <span className="field-label">Minimum disclosed duration (months)</span>
            <input
              type="number"
              min={0}
              max={24}
              value={duration}
              onChange={(event) => changeFilter(() => setDuration(event.target.value))}
            />
          </label>
          <label className="field">
            <span className="field-label">Minimum monthly stipend (INR)</span>
            <input
              type="number"
              min={0}
              max={1000000}
              step={1000}
              value={stipend}
              onChange={(event) => changeFilter(() => setStipend(event.target.value))}
            />
          </label>
          <label className="check-label">
            <input
              type="checkbox"
              checked={remote}
              onChange={(event) => changeFilter(() => setRemote(event.target.checked))}
            />
            Remote opportunities
          </label>
          <label className="check-label">
            <input
              type="checkbox"
              checked={paid}
              onChange={(event) => changeFilter(() => setPaid(event.target.checked))}
            />
            Paid internships / disclosed cash prizes
          </label>
          <label className="check-label">
            <input
              type="checkbox"
              checked={includeClosed}
              onChange={(event) => changeFilter(() => setIncludeClosed(event.target.checked))}
            />
            Include closed opportunities
          </label>
          <button className="text-link" onClick={reset}>
            Reset filters
          </button>
        </div>
        <div className="filter-sheet-actions">
          <Button variant="outline" onClick={cancelFilters}>
            Cancel
          </Button>
          <Button onClick={() => setFiltersOpen(false)}>Apply filters</Button>
        </div>
      </Modal>
      <div className="explorer-regions">
        <div className="region-tabs" role="group" aria-label="Opportunity region">
          {[
            ['all', 'Everywhere'],
            ['local', 'Near my cities'],
            ['india', 'Across India'],
            ['international', 'International'],
            ['worldwide', 'Worldwide location'],
            ['unknown', 'Location unknown'],
          ].map(([value, label]) => (
            <button
              key={value}
              aria-pressed={region === value}
              onClick={() =>
                changeFilter(() => {
                  setRegion(value);
                  setLocation('');
                })
              }
            >
              {label}
            </button>
          ))}
        </div>
        {region === 'local' && (
          <div className="region-tabs" role="group" aria-label="Local city">
            <button aria-pressed={!location} onClick={() => changeFilter(() => setLocation(''))}>
              All my local cities
            </button>
            {localCities.map((city) => (
              <button
                key={city}
                aria-pressed={location === city}
                onClick={() => changeFilter(() => setLocation(city))}
              >
                {city}
              </button>
            ))}
          </div>
        )}
      </div>
      <div className="results-bar results-heading" ref={resultsHeading} tabIndex={-1}>
        <span aria-live={resultsCurrent || error ? 'polite' : 'off'}>
          {!resultsCurrent ? (
            error ? (
              'Results unavailable'
            ) : total === null ? (
              'Loading opportunities…'
            ) : (
              'Updating results…'
            )
          ) : (
            <>
              <strong>{total ?? items.length}</strong>{' '}
              {total === null ? 'on this page' : total === 1 ? 'opportunity' : 'opportunities'}
            </>
          )}
          {loading && resultsCurrent && <LoaderCircle size={13} className="spin inline-loader" />}
        </span>
        <label className="sort-control">
          Sort by
          <select value={sort} onChange={(event) => changeFilter(() => setSort(event.target.value))}>
            <option value="score">Best match</option>
            <option value="newest">Newest first</option>
            <option value="deadline">Closing soon</option>
          </select>
        </label>
      </div>
      {error && (
        <div className="banner danger" role="alert">
          <span>{error}</span>
          <button
            onClick={() => {
              setCursors({ 1: '' });
              setPage(1);
              void result.refetch();
            }}
          >
            Try again
          </button>
        </div>
      )}
      <section
        ref={resultsPanel}
        className="panel opportunity-results"
        aria-label="Opportunity results"
        aria-busy={loading || (!resultsCurrent && !error)}
      >
        {!resultsCurrent ? (
          !error && (
            <div className="explorer-skeleton">
              <p className="results-updating" role="status">
                {total === null ? 'Loading opportunities…' : 'Updating results…'}
              </p>
              <div aria-hidden="true">
                {[0, 1, 2].map((row) => (
                  <div className="skeleton-row" key={row}>
                    <span className="skeleton-mark" />
                    <div className="skeleton-lines">
                      <span />
                      <span />
                      <span />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )
        ) : items.length ? (
          <div className="opportunity-list">{items.map(renderJob)}</div>
        ) : (
          !error && (
            <div className="empty">
              <div className="empty-icon">
                <copy.icon size={24} strokeWidth={1.6} />
              </div>
              <h3>
                {hasFilters
                  ? 'No opportunities match these filters'
                  : mode === 'saved'
                    ? 'Make room for your next move'
                    : mode === 'recommended'
                      ? 'Your recommendations are taking shape'
                      : mode === 'hackathon'
                        ? 'Your next challenge starts here'
                        : 'Your discovery feed is ready'}
              </h3>
              <p>
                {hasFilters
                  ? 'Broaden your filters to see more possibilities.'
                  : mode === 'saved'
                    ? 'Save an internship or hackathon using its bookmark. It will stay in this shortlist across visits.'
                    : mode === 'recommended'
                      ? 'Complete and verify your profile, then run discovery to find relevant opportunities.'
                      : 'Connect a permitted source and run discovery. Real opportunities will appear here with their source and deadline.'}
              </p>
              {hasFilters ? (
                <Button variant="outline" onClick={reset}>
                  Reset filters
                </Button>
              ) : (
                mode !== 'saved' && (
                  <Button variant="outline" onClick={onDiscover} disabled={busy || stopped}>
                    Run discovery
                  </Button>
                )
              )}
            </div>
          )
        )}
        {resultsCurrent &&
          (cursorMode ? page > 1 || result.data?.has_more : total !== null && total > pageSize) && (
            <div className="pagination">
              <span>
                Showing {(page - 1) * pageSize + 1}–{(page - 1) * pageSize + items.length}
                {total !== null ? ` of ${total}` : ''}
              </span>
              <div>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={loading || page <= 1}
                  onClick={() => changePage(page - 1)}
                >
                  <ArrowLeft size={14} />
                  Previous
                </Button>
                <span>
                  Page {page}
                  {total !== null ? ` of ${pages}` : ''}
                </span>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={loading || (cursorMode ? !result.data?.has_more : page >= pages)}
                  onClick={() => changePage(page + 1)}
                >
                  Next
                  <ArrowRight size={14} />
                </Button>
              </div>
            </div>
          )}
      </section>
      <div className="explorer-footer">
        <Link prefetch={false} className="text-link" href="/automation/sources">
          Manage locations and discovery sources
          <ArrowRight size={14} />
        </Link>
        <details className="location-help">
          <summary>Location and eligibility</summary>
          <p className="region-context">
            {region === 'local'
              ? `${localCities.length ? localCities.join(' and ') : 'No local cities selected'}. Edit your places below; nearby areas follow the named groups you enable.`
              : region === 'international'
                ? 'Listings with an identified overseas location. Check visa, relocation and whether Indian students can apply.'
                : region === 'worldwide'
                  ? 'The source explicitly lists a worldwide location. Check country restrictions and participation rules before applying.'
                  : 'Explore nearby, Indian and overseas opportunities separately. A remote label alone does not mean worldwide eligibility.'}
          </p>
        </details>
      </div>
      <p className="footnote">
        <Compass size={14} />
        Match scores explain fit. Eligibility, closing status, and your review determine the next step.
      </p>
    </>
  );
}

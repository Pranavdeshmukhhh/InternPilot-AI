'use client';
import { useEffect, useId, useMemo, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import * as Dialog from '@radix-ui/react-dialog';
import { ArrowUpRight, Search, X } from 'lucide-react';
import { routes, type View } from '@/lib/routes';
import type { Opportunity, OpportunityPage } from '@/lib/api-types';
import { useResource } from './provider';

const destinations: [View, string, string][] = [
  ['overview', 'Overview', 'Your next steps'],
  ['discover', 'Explore internships', 'Find a promising role'],
  ['hackathons', 'Hackathons', 'Build and compete'],
  ['recommended', 'Your matches', 'Profile-based recommendations'],
  ['saved', 'Saved opportunities', 'Your shortlist'],
  ['applications', 'Applications', 'Drafts, reviews and receipts'],
  ['documents', 'Documents', 'Resume versions and cover letters'],
  ['outreach', 'Recruiter outreach', 'Approved, relevant conversations'],
  ['automation', 'Automation center', 'Sources and worker activity'],
  ['sources', 'Discovery sources', 'Manage permitted publishers'],
  ['controls', 'Application policies', 'Modes, limits and emergency stop'],
  ['profile', 'Candidate profile', 'Verified facts and preferences'],
  ['security', 'Account security', 'Password and sessions'],
  ['notifications', 'Notifications', 'Updates and reminders'],
  ['owner', 'Owner console', 'Audited administration'],
];
export function CommandMenu({
  open,
  onClose,
  onOpen,
  owner,
}: {
  open: boolean;
  onClose: () => void;
  onOpen: (job: Opportunity) => void;
  owner: boolean;
}) {
  const [input, setInput] = useState('');
  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState(0);
  const [shortcuts, setShortcuts] = useState(true);
  const router = useRouter();
  const listId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  useEffect(() => {
    try {
      setShortcuts(localStorage.getItem('internpilot-shortcuts') !== 'off');
    } catch {}
  }, []);
  useEffect(() => {
    const timer = setTimeout(() => {
      setQuery(input.trim());
      setSelected(0);
    }, 300);
    return () => clearTimeout(timer);
  }, [input]);
  const jobs = useResource<OpportunityPage>(
    `/v2/opportunities?page_size=5&sort=newest&search=${encodeURIComponent(query)}`,
    query.length >= 2,
  );
  const commands = useMemo(
    () =>
      destinations
        .filter(
          ([id, label, description]) =>
            (owner || id !== 'owner') &&
            `${label} ${description}`.toLowerCase().includes(input.toLowerCase()),
        )
        .slice(0, 7),
    [input, owner],
  );
  const options = [
    ...commands.map(([id, label, description]) => ({
      id,
      label,
      description,
      run: () => router.push(routes[id]),
    })),
    ...(query.length >= 2 && query === input.trim() ? jobs.data?.items || [] : []).map((job) => ({
      id: job.id,
      label: job.title,
      description: job.company,
      run: () => onOpen(job),
    })),
  ];
  useEffect(() => {
    document.getElementById(`${listId}-${selected}`)?.scrollIntoView({ block: 'nearest' });
  }, [listId, selected]);
  const activate = (index: number) => {
    const item = options[index];
    if (item) {
      onClose();
      item.run();
    }
  };
  return (
    <Dialog.Root open={open} onOpenChange={(value) => !value && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="modal-overlay" />
        <Dialog.Content
          className="command-menu"
          onOpenAutoFocus={(event) => {
            event.preventDefault();
            inputRef.current?.focus();
          }}
        >
          <Dialog.Title className="sr-only">Find anything in your workspace</Dialog.Title>
          <Dialog.Description className="sr-only">
            Search destinations and your opportunities. Use arrow keys and Enter to open.
          </Dialog.Description>
          <div className="command-input">
            <Search size={20} />
            <input
              ref={inputRef}
              role="combobox"
              aria-autocomplete="list"
              aria-expanded={true}
              aria-controls={listId}
              aria-activedescendant={options[selected] ? `${listId}-${selected}` : undefined}
              aria-label="Search workspace"
              placeholder="Where would you like to go?"
              value={input}
              onChange={(e) => {
                setInput(e.target.value);
                setSelected(0);
              }}
              onKeyDown={(event) => {
                if (event.nativeEvent.isComposing) return;
                if (event.key === 'ArrowDown') {
                  event.preventDefault();
                  setSelected((i) => Math.min(i + 1, options.length - 1));
                }
                if (event.key === 'ArrowUp') {
                  event.preventDefault();
                  setSelected((i) => Math.max(0, i - 1));
                }
                if (event.key === 'Enter') {
                  event.preventDefault();
                  activate(selected);
                }
              }}
            />
            <Dialog.Close className="icon-btn" aria-label="Close command menu">
              <X size={18} />
            </Dialog.Close>
          </div>
          <div role="listbox" id={listId} aria-label="Search results" className="command-results">
            {options.map((item, index) => (
              <div
                id={`${listId}-${index}`}
                key={item.id}
                role="option"
                aria-selected={selected === index}
                className={`command-result ${selected === index ? 'selected' : ''}`}
                onPointerMove={() => setSelected(index)}
                onClick={() => activate(index)}
              >
                <span>
                  <strong>{item.label}</strong>
                  <small>{item.description}</small>
                </span>
                <ArrowUpRight size={15} />
              </div>
            ))}
            {!options.length && (
              <p className="inline-empty">
                {jobs.isFetching
                  ? 'Searching your opportunities…'
                  : jobs.isError
                    ? 'Search is unavailable. Navigation is still available.'
                    : 'No results. Try a role, employer or workspace destination.'}
              </p>
            )}
          </div>
          <div className="command-footer">
            <span>
              <kbd>↑</kbd>
              <kbd>↓</kbd> to move · <kbd>↵</kbd> to open
            </span>
            <label>
              <input
                type="checkbox"
                checked={shortcuts}
                onChange={(event) => {
                  setShortcuts(event.target.checked);
                  try {
                    localStorage.setItem('internpilot-shortcuts', event.target.checked ? 'on' : 'off');
                  } catch {}
                }}
              />
              Enable / search shortcut
            </label>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

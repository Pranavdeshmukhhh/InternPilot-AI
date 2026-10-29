'use client';

import { useEffect, useState } from 'react';
import { MapPin, LoaderCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { SourceCatalog } from '@/components/source-catalog';
import { SourceCandidates } from '@/components/source-candidates';

type Props = {
  api: (path: string, method?: string, body?: unknown) => Promise<any>;
  busy: boolean;
  onChanged: () => Promise<void>;
};

export function RegionalDiscovery({ api, busy, onChanged }: Props) {
  const [config, setConfig] = useState<Record<string, any> | null>(null);
  const [cities, setCities] = useState('');
  const [nearby, setNearby] = useState(true);
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [reload, setReload] = useState(0);
  useEffect(() => {
    let current = true;
    api('/discovery/regions')
      .then((value) => {
        if (current) {
          setConfig(value);
          setCities(value.local_cities.join(', '));
          setNearby(value.include_nearby);
          setError('');
        }
      })
      .catch((reason) => {
        if (current) setError(reason.message);
      });
    return () => {
      current = false;
    };
  }, [api, reload]);
  const save = async () => {
    setPending(true);
    setError('');
    setMessage('');
    try {
      const profile = await api('/profile');
      await api('/profile', 'PUT', {
        ...profile,
        preferred_local_cities: cities
          .split(',')
          .map((city) => city.trim())
          .filter(Boolean),
        include_nearby_locations: nearby,
      });
      setMessage('Local preferences saved.');
      setReload((value) => value + 1);
      await onChanged();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Unable to save preferences.');
    } finally {
      setPending(false);
    }
  };
  const enable = async () => {
    setPending(true);
    setError('');
    setMessage('');
    try {
      const result = await api('/discovery/regions/enable', 'POST');
      setMessage(
        `${result.added} regional search sources added. Run Find opportunities or leave the worker running.`,
      );
      setReload((value) => value + 1);
      await onChanged();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Unable to enable regional search.');
    } finally {
      setPending(false);
    }
  };
  const missing =
    config?.search_presets.filter((preset: Record<string, any>) => !preset.installed).length || 0;
  return (
    <details className="regional-discovery">
      <summary>
        <MapPin size={16} />
        Local places & discovery coverage
      </summary>
      <p>
        Official employer boards cover their published locations. The India feed and MLH calendar add
        internship references and hackathons. Local availability depends on what each source publishes.
      </p>
      <div className="regional-settings">
        <label className="field">
          <span className="field-label">Your local cities</span>
          <input
            value={cities}
            onChange={(event) => setCities(event.target.value)}
            placeholder="Nagpur, Pune"
          />
        </label>
        <label className="check-label">
          <input type="checkbox" checked={nearby} onChange={(event) => setNearby(event.target.checked)} />
          Include named nearby places
        </label>
        <Button variant="outline" size="sm" disabled={pending || busy || !config} onClick={save}>
          Save local preferences
        </Button>
      </div>
      {config && nearby && (
        <p className="footnote">
          Nearby groups:{' '}
          {Object.entries(config.nearby_places)
            .map(([city, places]) => `${city}: ${(places as string[]).join(', ')}`)
            .join(' · ')}
          . These are named areas, not a distance-based search.
        </p>
      )}
      <p>
        {config?.search_configured
          ? 'Regional web search is configured. Enable the queries below to search public announcements beyond your connected boards.'
          : 'Broader local and international web search needs BRAVE_SEARCH_API_KEY in the server configuration. Your connected public sources still work without it.'}
      </p>
      {config && (
        <details className="regional-query-list">
          <summary>View regional search queries</summary>
          <ul>
            {config.search_presets.map((preset: Record<string, any>) => (
              <li key={preset.slug}>
                <strong>{preset.company}</strong>
                <span>{preset.slug}</span>
                <small>
                  {preset.installed
                    ? 'Configured source — check its enabled state under Discovery sources'
                    : 'Not added'}
                </small>
              </li>
            ))}
          </ul>
        </details>
      )}
      {config?.search_configured && (
        <Button variant="outline" size="sm" disabled={pending || busy || !missing} onClick={enable}>
          {pending && <LoaderCircle size={14} className="spin" />}
          {missing ? 'Enable regional search sources' : 'Regional search sources added'}
        </Button>
      )}
      <SourceCatalog
        api={api}
        onChanged={() => {
          setReload((value) => value + 1);
          onChanged();
        }}
      />
      <SourceCandidates
        api={api}
        onChanged={() => {
          setReload((value) => value + 1);
          onChanged();
        }}
      />
      {message && <p role="status">{message}</p>}
      {error && (
        <p className="banner danger" role="alert">
          {error}
        </p>
      )}
    </details>
  );
}

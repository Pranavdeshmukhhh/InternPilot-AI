'use client';

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react';
import { QueryClient, QueryClientProvider, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, ApiError, sessionEpoch, setApiSession } from '@/lib/api-client';
import { resourceKey, mutationResources, isPath } from '@/lib/query-keys';
import type { Session } from '@/lib/api-types';

const SessionContext = createContext<{
  session: Session | null;
  checking: boolean;
  sessionError: string | null;
  retrySession: () => void;
  login: (value: Session) => void;
  clear: () => void;
}>({
  session: null,
  checking: true,
  sessionError: null,
  retrySession: () => {},
  login: () => {},
  clear: () => {},
});
export const useSession = () => useContext(SessionContext);

function SessionProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [session, setSession] = useState<Session | null>(null);
  const [checking, setChecking] = useState(true);
  const [sessionError, setSessionError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const retrySession = useCallback(() => setAttempt((value) => value + 1), []);
  const clear = useCallback(() => {
    setApiSession();
    void queryClient.cancelQueries();
    queryClient.clear();
    setSession(null);
    setSessionError(null);
  }, [queryClient]);
  const login = useCallback(
    (value: Session) => {
      setApiSession(value.csrf_token);
      void queryClient.cancelQueries();
      queryClient.clear();
      setSession(value);
      setSessionError(null);
    },
    [queryClient],
  );
  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    setChecking(true);
    setSessionError(null);
    api<Session>('/auth/session', 'GET', undefined, false, controller.signal)
      .then((value) => {
        if (active) login(value);
      })
      .catch((error: unknown) => {
        if (!active || (error instanceof ApiError && error.status === 401)) return;
        // A network failure, throttle, or server error does not invalidate a cookie.
        setSessionError(
          'The account service is temporarily unavailable. Try again to reopen your workspace.',
        );
      })
      .finally(() => {
        if (active) setChecking(false);
      });
    window.addEventListener('internpilot:unauthorized', clear);
    return () => {
      active = false;
      controller.abort();
      window.removeEventListener('internpilot:unauthorized', clear);
    };
  }, [login, clear, attempt]);
  return (
    <SessionContext.Provider value={{ session, checking, sessionError, retrySession, login, clear }}>
      {children}
    </SessionContext.Provider>
  );
}

export function Providers({ children }: { children: ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 60_000,
            gcTime: 300_000,
            refetchOnWindowFocus: false,
            retry: (count, error) => count < 1 && !(error instanceof ApiError && error.status < 500),
          },
          mutations: { retry: false },
        },
      }),
  );
  return (
    <QueryClientProvider client={client}>
      <SessionProvider>{children}</SessionProvider>
    </QueryClientProvider>
  );
}

export function useResource<T>(path: string, enabled = true, staleTime = 60_000, debounce = 0) {
  const { session } = useSession();
  return useQuery<T>({
    queryKey: resourceKey(session?.user.id || '', sessionEpoch(), path),
    queryFn: async ({ signal }) => {
      if (debounce)
        await new Promise<void>((resolve, reject) => {
          const done = () => {
            signal.removeEventListener('abort', abort);
            resolve();
          };
          const timer = setTimeout(done, debounce);
          const abort = () => {
            clearTimeout(timer);
            reject(new DOMException('Request cancelled', 'AbortError'));
          };
          signal.addEventListener('abort', abort, { once: true });
        });
      return api<T>(path, 'GET', undefined, false, signal);
    },
    enabled: !!session && enabled,
    staleTime,
  });
}

export function useInvalidation() {
  const client = useQueryClient();
  const { session } = useSession();
  return useCallback(
    async (key: string) => {
      const groups = mutationResources[key.split('-')[0]] || [
        '/applications',
        '/documents',
        '/sources',
        '/operations',
        '/tasks',
        '/events',
        '/notifications',
      ];
      await client.invalidateQueries({
        predicate: (query) =>
          query.queryKey[1] === session?.user.id &&
          typeof query.queryKey[3] === 'string' &&
          groups.some((prefix) => isPath(query.queryKey[3] as string, prefix)),
      });
    },
    [client, session?.user.id],
  );
}

/** Coalesce generic server hints. Only active view queries refetch; forms stay dirty. */
export function useWorkspaceEvents() {
  const { session } = useSession();
  const client = useQueryClient();
  useEffect(() => {
    if (!session) return;
    let scheduled: ReturnType<typeof setTimeout> | undefined;
    let healthy = false;
    let missed = false;
    const refresh = () => {
      if (document.hidden) {
        missed = true;
        return;
      }
      if (scheduled) return;
      scheduled = setTimeout(() => {
        scheduled = undefined;
        if (document.hidden) {
          missed = true;
          return;
        }
        missed = false;
        void client.invalidateQueries({
          predicate: (q) =>
            q.queryKey[1] === session.user.id &&
            !['/profile', '/policy', '/health', '/notification-settings'].includes(String(q.queryKey[3])) &&
            q.getObserversCount() > 0,
        });
      }, 600);
    };
    const stream = new EventSource('/api/events/stream');
    stream.addEventListener('ready', () => {
      healthy = true;
    });
    stream.onmessage = refresh;
    stream.onerror = () => {
      healthy = false;
    };
    const fallback = setInterval(() => {
      if (!healthy) refresh();
    }, 60_000);
    const resume = () => {
      if (!document.hidden && (missed || !healthy)) refresh();
    };
    document.addEventListener('visibilitychange', resume);
    return () => {
      stream.close();
      clearInterval(fallback);
      if (scheduled) clearTimeout(scheduled);
      document.removeEventListener('visibilitychange', resume);
    };
  }, [session, client]);
}

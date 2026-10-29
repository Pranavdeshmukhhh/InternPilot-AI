import type { LegacyItem } from './legacy-types';

let csrf = '';
let epoch = 0;
export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}
export const sessionEpoch = () => epoch;
export function setApiSession(token = '') {
  epoch += 1;
  csrf = token;
}

/** Cookies stay HttpOnly; CSRF and session generation never enter persisted caches. */
export async function api<T = LegacyItem>(
  path: string,
  method = 'GET',
  body?: unknown,
  binary = false,
  signal?: AbortSignal,
): Promise<T> {
  const generation = epoch;
  const form = typeof FormData !== 'undefined' && body instanceof FormData;
  const response = await fetch(`/api${path}`, {
    method,
    signal,
    credentials: 'same-origin',
    cache: 'no-store',
    headers: {
      ...(form || body === undefined ? {} : { 'Content-Type': 'application/json' }),
      ...(method !== 'GET' && csrf ? { 'X-CSRF-Token': csrf } : {}),
    },
    ...(body === undefined ? {} : { body: form ? (body as FormData) : JSON.stringify(body) }),
  });
  if (generation !== epoch) throw new ApiError('Session changed; the older response was discarded.', 409);
  if (!response.ok) {
    const data: unknown = await response.json().catch(() => null);
    const detail = data && typeof data === 'object' && 'detail' in data ? data.detail : null;
    const message =
      typeof detail === 'string'
        ? detail
        : Array.isArray(detail)
          ? detail.map((item: { msg?: string }) => item.msg || 'Invalid field').join('; ')
          : `Request failed (${response.status}).`;
    if (response.status === 401) window.dispatchEvent(new Event('internpilot:unauthorized'));
    throw new ApiError(message, response.status);
  }
  const result: unknown =
    response.status === 204 ? undefined : binary ? await response.blob() : await response.json();
  if (generation !== epoch) throw new ApiError('Session changed; the older response was discarded.', 409);
  return result as T;
}

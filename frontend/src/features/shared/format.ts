import type { LegacyItem as Item } from '@/lib/legacy-types';
export const human = (v: unknown) =>
  typeof v === 'string' ? v.replaceAll('_', ' ').replace(/\b\w/g, (x) => x.toUpperCase()) : 'Unknown';
export const fmt = (v: number | null | undefined) =>
  v == null ? '—' : Intl.NumberFormat('en-IN', { maximumFractionDigits: 1 }).format(v);
export const list = (v: unknown): Item[] =>
  Array.isArray(v) ? v : v && typeof v === 'object' && 'items' in v && Array.isArray(v.items) ? v.items : [];
export function timestamp(v: unknown) {
  if (!v) return 'Not recorded';
  const d = new Date(String(v));
  return Number.isNaN(d.getTime())
    ? String(v)
    : d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}
export function ago(v: unknown) {
  if (!v) return 'Time unknown';
  const t = Date.now() - new Date(String(v)).getTime();
  if (t < 60000) return 'Just now';
  if (t < 3600000) return `${Math.floor(t / 60000)}m ago`;
  if (t < 86400000) return `${Math.floor(t / 3600000)}h ago`;
  return `${Math.floor(t / 86400000)}d ago`;
}
export function clean(v: unknown): string {
  return String(v || '')
    .replace(/<[^>]*>/g, ' ')
    .replace(/&nbsp;/g, ' ')
    .replace(/&amp;/g, '&')
    .replace(/\s+/g, ' ')
    .trim();
}
export function url(v: unknown) {
  try {
    const u = new URL(String(v));
    return ['https:', 'http:'].includes(u.protocol) ? u.href : undefined;
  } catch {
    return undefined;
  }
}
export function evaluation(j: Item) {
  return { ...j, ...(j.evaluation || {}), ...(j.match_evaluation || {}) };
}

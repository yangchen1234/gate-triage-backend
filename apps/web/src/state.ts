import type { Container, Job } from './types.ts';

export type Filters = { search: string; action: string; cargo: string; conflict: boolean; sort: string };
export const DEFAULT_FILTERS: Filters = { search: '', action: 'all', cargo: 'all', conflict: false, sort: 'priority' };
export type RequestIntent = { key: string; revision: number; top_n: number; use_model: boolean };

export function requestIntent(previous: RequestIntent | null, revision: number, top_n: number, use_model: boolean, createKey: () => string): RequestIntent {
  if (previous && previous.revision === revision && previous.top_n === top_n && previous.use_model === use_model) return previous;
  return { key: createKey(), revision, top_n, use_model };
}

export function filterQueue(queue: Container[], filters: Filters): Container[] {
  const query = filters.search.trim().toLowerCase();
  const rows = queue.filter(row => (!query || `${row.container_id} ${row.carrier_code} ${row.consignee_type}`.toLowerCase().includes(query)) &&
    (filters.action === 'all' || row.action === filters.action) && (filters.cargo === 'all' || row.cargo_type === filters.cargo) &&
    (!filters.conflict || row.conflict_score >= 0.5));
  return [...rows].sort((a, b) => filters.sort === 'fee' ? b.demurrage_per_day - a.demurrage_per_day :
    filters.sort === 'arrival' ? a.arrived_at.localeCompare(b.arrived_at) : b.priority - a.priority);
}

export function jobIsStale(job: Job | null, revision: number): boolean {
  return !!job && (job.stale || job.input_revision !== revision);
}

export function jobIsRunning(job: Job | null): boolean {
  return !!job && ['queued', 'running'].includes(job.status);
}

export function preferredPlanId(jobs: Job[], previous: string | null): string | null {
  return jobs.find(jobIsRunning)?.id || (jobs.some(job => job.id === previous) ? previous : jobs[0]?.id || null);
}

export function mayDecide(job: Job | null, revision: number): boolean {
  return !!job && job.status === 'succeeded' && !jobIsStale(job, revision);
}

export function mergeJob(jobs: Job[], incoming: Job): Job[] {
  const previous = jobs.find(job => job.id === incoming.id);
  // A delayed poll must not replace a completed response with an older running response.
  if (previous && !jobIsRunning(previous) && jobIsRunning(incoming)) return jobs;
  return [incoming, ...jobs.filter(job => job.id !== incoming.id)].slice(0, 40);
}

export function money(amount: number, currency = 'USD'): string {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency, maximumFractionDigits: 0 }).format(amount);
}

export function humanize(value: string): string {
  return value.replaceAll('_', ' ').replace(/\b\w/g, char => char.toUpperCase());
}

export function dateTime(value: string): string {
  const date = new Date(/[zZ]|[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

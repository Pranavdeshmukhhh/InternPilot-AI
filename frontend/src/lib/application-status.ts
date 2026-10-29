// Unknown states remain visible for review instead of disappearing from the board.
export function applicationStage(status: string): 'Preparing' | 'Review' | 'Follow-up' | 'Closed' {
  if (['queued', 'preparing', 'ready', 'approved', 'submitting'].includes(status)) return 'Preparing';
  if (['submitted', 'assessment', 'interview'].includes(status)) return 'Follow-up';
  if (['offer', 'rejected', 'withdrawn'].includes(status)) return 'Closed';
  return 'Review';
}
export function applicationMatches(status: string, filter: string) {
  if (!filter) return true;
  if (filter === 'attention') return applicationStage(status) === 'Review';
  if (filter === 'progress') return applicationStage(status) === 'Preparing';
  if (filter === 'submitted') return status === 'submitted';
  return false;
}

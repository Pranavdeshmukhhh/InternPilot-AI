export const resourceKey = (owner: string, epoch: number, path: string) =>
  ['private', owner, epoch, path] as const;
export const mutationResources: Record<string, readonly string[]> = {
  save: ['/opportunities', '/v2/opportunities', '/dashboard'],
  profile: ['/profile', '/opportunities', '/v2/opportunities', '/dashboard'],
  policy: ['/policy', '/operations'],
  source: ['/sources', '/operations', '/opportunities', '/v2/opportunities', '/dashboard'],
  prepare: ['/applications', '/tasks'],
  doc: ['/documents'],
  notification: ['/notifications'],
  stop: ['/policy', '/operations'],
  discover: ['/tasks', '/sources', '/operations'],
};
export const isPath = (path: string, prefix: string) =>
  path === prefix || path.startsWith(prefix + '/') || path.startsWith(prefix + '?');

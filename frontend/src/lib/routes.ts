export const routes = {
  overview: '/overview',
  discover: '/explore/internships',
  hackathons: '/explore/hackathons',
  recommended: '/explore/matches',
  saved: '/saved',
  applications: '/applications',
  documents: '/documents',
  outreach: '/outreach',
  automation: '/automation',
  sources: '/automation/sources',
  controls: '/automation/policies',
  activity: '/automation/activity',
  notifications: '/notifications',
  profile: '/settings/profile',
  security: '/settings/security',
  owner: '/owner',
} as const;
export type View = keyof typeof routes;
export const viewForPath = (path: string): View | undefined =>
  (Object.keys(routes) as View[]).find((view) => routes[view] === path);

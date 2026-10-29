// No invented deployment URL. Social/canonical URLs exist only after configuration.
function origin(value: string | undefined): URL | undefined {
  if (!value) return;
  try {
    const url = new URL(value);
    if (
      url.protocol === 'https:' &&
      !url.username &&
      !url.password &&
      url.pathname === '/' &&
      !url.search &&
      !url.hash
    )
      return url;
  } catch {
    /* Unconfigured preview. */
  }
}
export const siteOrigin = origin(process.env.PUBLIC_SITE_URL);
const candidateWorkspace = origin(process.env.PUBLIC_WORKSPACE_URL);
export const workspaceOrigin =
  candidateWorkspace?.origin !== siteOrigin?.origin ? candidateWorkspace : undefined;

export const workspaceAvailable = process.env.PUBLIC_DEMO_ONLY !== 'true';

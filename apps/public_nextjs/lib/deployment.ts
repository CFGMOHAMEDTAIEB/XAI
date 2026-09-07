function configured(name: string, value: string | undefined, fallback: string): string {
  if (!value || value.includes('REPLACE_')) {
    if (process.env.VERCEL) throw new Error(`Set ${name} to the deployed HTTPS URL`);
    return fallback;
  }
  const url = new URL(value);
  if (process.env.VERCEL && (url.protocol !== 'https:' || ['localhost','127.0.0.1','10.0.2.2','backend'].includes(url.hostname))) {
    throw new Error(`${name} must use the deployed HTTPS origin`);
  }
  return url.origin;
}
export const siteUrl = configured('NEXT_PUBLIC_SITE_URL', process.env.NEXT_PUBLIC_SITE_URL, 'http://localhost:3000');
export const portalUrl = configured('NEXT_PUBLIC_APP_URL', process.env.NEXT_PUBLIC_APP_URL, 'http://localhost:4200');
export const apiUrl = configured('INTERNAL_API_URL', process.env.INTERNAL_API_URL, 'http://localhost:8000');

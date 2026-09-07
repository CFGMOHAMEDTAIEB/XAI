import {writeFileSync} from 'node:fs';
const raw = process.env.XAI_API_URL;
if (!raw || raw.includes('REPLACE_')) throw new Error('Set XAI_API_URL to the real Render HTTPS API origin before building.');
const url = new URL(raw);
if (url.protocol !== 'https:' || url.username || url.password || url.search || url.hash || url.pathname !== '/') {
  throw new Error('XAI_API_URL must be an HTTPS origin without credentials, path, query or fragment.');
}
const site = process.env.NEXT_PUBLIC_SITE_URL;
if (!site || site.includes('REPLACE_')) throw new Error('Set NEXT_PUBLIC_SITE_URL for the portal return link.');
function publicOrigin(value) {
  const parsed = new URL(value);
  if (parsed.protocol !== 'https:' || parsed.username || parsed.password || parsed.pathname !== '/' || parsed.search || parsed.hash) throw new Error('Expected a public HTTPS origin.');
  return parsed.origin;
}
const publicSiteUrl = publicOrigin(site);
const adminUrl = process.env.ADMIN_URL ? publicOrigin(process.env.ADMIN_URL) : '';
writeFileSync(new URL('../src/environments/environment.vercel.ts', import.meta.url),
  'export const environment = ' + JSON.stringify({production:true,apiUrl:url.origin,demoMode:false,publicSiteUrl,adminUrl}) + ';\n');
console.log('Configured public API origin for Vercel build.');

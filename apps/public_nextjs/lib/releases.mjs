// Only reviewed production metadata can produce a public download link.
export function productionReleases(manifest) {
  if (!manifest || manifest.schemaVersion !== 1 || !Array.isArray(manifest.releases)) return [];
  return manifest.releases.filter(release => {
    if (!release || release.channel !== 'PRODUCTION' || release.signing !== 'VERIFIED' || release.installTest !== 'PASSED') return false;
    if (!['android','windows','ios','macos','linux','cli'].includes(release.platform)) return false;
    if (!['version','filename','architecture','releaseNotes'].every(key => typeof release[key] === 'string' && release[key].trim())) return false;
    if (!/^[a-zA-Z0-9._-]+$/.test(release.filename) || !/^[a-fA-F0-9]{64}$/.test(release.sha256)) return false;
    if (!Number.isSafeInteger(release.sizeBytes) || release.sizeBytes <= 0 || !Number.isFinite(Date.parse(release.releasedAt))) return false;
    try {
      // Hosting is restricted to version-tag assets on GitHub Releases.
      // No local paths, credentials, arbitrary redirect services, or latest aliases.
      const url = new URL(release.url);
      return url.protocol === 'https:' && url.hostname === 'github.com' && !url.port && !url.username && !url.password && !url.search && !url.hash &&
        /^\/CFGMOHAMEDTAIEB\/XAI\/releases\/download\/[^/]+\/[^/]+$/.test(url.pathname) &&
        decodeURIComponent(url.pathname.split('/').at(-1)) === release.filename;
    } catch { return false; }
  });
}

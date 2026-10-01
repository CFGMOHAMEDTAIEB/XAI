import {
  Box,
  CalendarDays,
  Download,
  FileArchive,
  FileCode2,
  Monitor,
  ShieldAlert,
  Smartphone,
  Terminal,
} from 'lucide-react';

import {localArtifacts, type LocalArtifact} from '@/lib/local-releases';

export const dynamic = 'force-dynamic';
export const metadata = {
  title: 'Downloads',
  description: 'Download available XAICD client packages.',
};

type ArtifactPresentation = {
  product: string;
  label: string;
  description: string;
  format: string;
  icon: typeof Smartphone;
};

const presentations: ArtifactPresentation[] = [
  {
    product: 'XAICD Authenticator',
    label: 'XAICD Authenticator',
    description: 'Companion authenticator for account verification and rotating sign-in codes.',
    format: 'APK',
    icon: Smartphone,
  },
  {
    product: 'XAICD Desktop',
    label: 'XAICD Desktop',
    description: 'Focused Windows client for authenticated compression, decompression, history, and sharing.',
    format: 'ZIP application package',
    icon: Monitor,
  },
  {
    product: 'XAICD CLI',
    label: 'XAICD CLI',
    description: 'Command-line tools for scripted compression and restoration workflows.',
    format: 'Python wheel',
    icon: Terminal,
  },
];

function formatSize(value: number) {
  return new Intl.NumberFormat('en', {
    style: 'unit',
    unit: 'megabyte',
    maximumFractionDigits: value < 1024 * 1024 ? 2 : 1,
  }).format(value / 1024 / 1024);
}

function formatDate(value: string) {
  const parsed = new Date(value);
  return Number.isNaN(parsed.valueOf())
    ? 'Date unavailable'
    : new Intl.DateTimeFormat('en', {dateStyle: 'medium'}).format(parsed);
}

function ArtifactCard({item, presentation}: {item: LocalArtifact; presentation: ArtifactPresentation}) {
  const Icon = presentation.icon;

  return (
    <article className="download-card">
      <header className="download-card-header">
        <span className="download-product-icon" aria-hidden="true"><Icon /></span>
        <span className="evaluation-badge">Available package</span>
      </header>

      <div className="download-card-copy">
        <p className="download-platform">{item.platform}</p>
        <h2>{presentation.label}</h2>
        <p>{presentation.description}</p>
      </div>

      <dl className="download-metadata">
        <div><dt>Format</dt><dd><FileArchive size={16} />{presentation.format}</dd></div>
        <div><dt>Version</dt><dd><Box size={16} />{item.version}</dd></div>
        <div><dt>Architecture</dt><dd><FileCode2 size={16} />{item.architecture}</dd></div>
        <div><dt>File size</dt><dd>{formatSize(item.size)}</dd></div>
      </dl>

      <details className="integrity-details">
        <summary>Integrity details</summary>
        <dl>
          <div><dt>File</dt><dd>{item.filename}</dd></div>
          <div><dt>SHA-256</dt><dd><code>{item.sha256}</code></dd></div>
          <div><dt>Publisher signature</dt><dd>{item.signed ? 'Verified' : 'Not provided'}</dd></div>
          <div><dt>Built</dt><dd><CalendarDays size={15} />{formatDate(item.buildDate)}</dd></div>
          <div><dt>Requirements</dt><dd>{item.minimumRequirements}</dd></div>
        </dl>
      </details>

      <a
        className="button download-button"
        href={`/api/releases/${encodeURIComponent(item.filename)}`}
        aria-label={`Download ${presentation.label} ${item.version}`}
      >
        <Download size={18} />Download
      </a>
    </article>
  );
}

export default function Downloads() {
  const artifacts = localArtifacts();
  const available = presentations.flatMap((presentation) => {
    const item = artifacts.find((candidate) => candidate.product === presentation.product);
    return item ? [{item, presentation}] : [];
  });

  return (
    <main className="downloads-page">
      <section className="downloads-intro">
        <div className="container downloads-intro-grid">
          <div>
            <span className="eyebrow">Client packages</span>
            <h1>XAICD Downloads</h1>
            <p>Choose the client that matches your workflow.</p>
            <p className="downloads-summary">
              Every enabled download maps to an artifact verified against the local release manifest. Expand
              integrity details to review its filename, checksum, signing state, build date, and requirements.
            </p>
          </div>
        </div>
      </section>

      <section className="downloads-catalog" aria-labelledby="download-catalog-title">
        <div className="container">
          <div className="catalog-heading">
            <div><span>Available packages</span><h2 id="download-catalog-title">Select your client</h2></div>
            <p>{available.length} manifest-verified artifact{available.length === 1 ? '' : 's'}</p>
          </div>
          {available.length > 0 ? (
            <div className="download-card-grid">
              {available.map(({item, presentation}) => (
                <ArtifactCard key={item.filename} item={item} presentation={presentation} />
              ))}
            </div>
          ) : (
            <div className="downloads-empty" role="status">
              <ShieldAlert />
              <div><h2>No verified local artifacts are available</h2><p>Generate and validate the release manifest before offering downloads.</p></div>
            </div>
          )}
        </div>
      </section>
    </main>
  );
}

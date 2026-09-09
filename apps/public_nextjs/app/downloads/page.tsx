import {SectionHeading} from '@/components/section-heading';
import manifest from '@/lib/releases.json';
import {productionReleases} from '@/lib/releases.mjs';
export const metadata={title:'Downloads'};
const platforms=[['android','Android Authenticator'],['windows','Windows desktop'],['ios','iOS Authenticator'],['macos','macOS desktop'],['linux','Linux desktop'],['cli','Command-line engine']];
export default function Downloads(){
 const releases=productionReleases(manifest);
 return <section className="page-hero"><div className="container"><SectionHeading eyebrow="Application availability" title="Production releases" body="Only reviewed, signed and installation-tested production releases are listed for download. Source code and local test builds are not production distribution."/><div className="download-grid">{platforms.map(([platform,label])=>{
 const release=releases.find(r=>r.platform===platform);
 return <article key={platform}><h2>{label}</h2>{release?<><p>{release.version} · {release.architecture}</p><p>{release.sizeBytes.toLocaleString()} bytes · {release.releasedAt}</p><p>{release.releaseNotes}</p><p style={{overflowWrap:'anywhere'}}>SHA-256: {release.sha256}</p><a className="button" href={release.url}>Download {release.filename}</a></>:<><p>{label} release is not available yet.</p><button className="button" disabled>Download unavailable</button></>}</article>;
 })}</div><p>Historical Android builds used debug signing and Windows builds were unsigned. These are test artifacts, not public production releases.</p></div></section>;
}

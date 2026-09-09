import {Download,Monitor,ShieldCheck,Terminal} from 'lucide-react';
import {SectionHeading} from '@/components/section-heading';
export const metadata={title:'Downloads'};
const downloads=[
 {i:ShieldCheck,t:'Android Authenticator',p:'Android · 0.1.0+1',d:'Local test builds only. Public distribution is pending release signing and validation on the target phone.',status:'Test build — not publicly hosted'},
 {i:Monitor,t:'Windows desktop',p:'Windows · 0.1.0+1',d:'Local unsigned builds support cloud compression and decompression. Public distribution is pending signing and validation.',status:'Unsigned test build — not publicly hosted'},
 {i:ShieldCheck,t:'iOS Authenticator',p:'iOS',d:'No distributable iOS build is available. Apple signing and the macOS/Xcode distribution workflow are required.',status:'Coming soon'},
 {i:Terminal,t:'Command-line engine',p:'Python · Rust extension',d:'Source-based compression, decompression and reproducible benchmarks. No verified public binary package is published.',status:'Release pending'},
];
export default function Downloads(){return <section className="page-hero"><div className="container"><SectionHeading eyebrow="Applications" title="Choose the interface for each workflow" body="Public downloads are pending release validation and signing. Local test builds are not production releases."/><div className="download-grid">{downloads.map(({i:I,t,p,d,status})=><article key={t}><I/><h2>{t}</h2><b>{p}</b><p>{d}</p><p>{status}</p><button className="button" disabled><Download size={17}/>Download unavailable</button></article>)}</div><div className="notice-box"><b>No public production binary yet</b><p>Download links will appear when hosted artifacts, checksums and release signing have been verified. There is currently no public macOS or Linux desktop package.</p></div></div></section>}

import {SectionHeading} from '@/components/section-heading';
import {apiUrl} from '@/lib/deployment';
import {normalizeStatus,serviceLabels} from '@/lib/status.mjs';
export const dynamic='force-dynamic';
export const metadata={title:'Status'};
export default async function Status(){
 let state=normalizeStatus(null);
 let error=false;
 try{
  const response=await fetch(`${apiUrl}/public/status`,{cache:'no-store',signal:AbortSignal.timeout(8000)});
  if(!response.ok)throw new Error('Status unavailable');
  state=normalizeStatus(await response.json());
 }catch{error=true;}
 return <section className="page-hero"><div className="container narrow"><SectionHeading eyebrow="Service readiness" title={error?'Status unavailable':`Platform: ${state.overall}`} body="Read-only backend prerequisite checks. Unknown means a dependency has not been verified."/>{error&&<p role="alert">Could not retrieve current status. Service states are unknown. Reload to retry.</p>}<div className="status-list">{Object.entries(serviceLabels).map(([key,label])=><div key={key}><b>{label}</b><span className="status-pill">{state.services[key]}</span></div>)}</div><p>Database connectivity does not verify a login. Compression prerequisites do not establish successful processing. Storage readiness does not guarantee persistence. Notification configuration does not prove delivery.</p><p>Historical monitoring and uptime percentages are not available. No email is sent by these checks.</p></div></section>;
}

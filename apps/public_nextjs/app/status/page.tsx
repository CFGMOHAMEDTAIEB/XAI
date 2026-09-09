import {SectionHeading} from '@/components/section-heading';
import {apiUrl} from '@/lib/deployment';
export const dynamic = 'force-dynamic';
export const metadata = {title:'Status'};
const labels: Record<string,string> = {api:'API',identity:'Account authentication',compression:'Compression readiness',storage:'File storage readiness',notifications:'Notifications',security_scanner:'Security scanner readiness'};
const allowed = ['operational','degraded','unavailable','unknown'];
export default async function Status(){
  let overall = 'unavailable';
  let services: Record<string,string> = Object.fromEntries(Object.keys(labels).map(key=>[key,'unknown']));
  try {
    const response = await fetch(`${apiUrl}/public/status`, {cache:'no-store',signal:AbortSignal.timeout(8000)});
    if(response.ok){const data=await response.json();overall=allowed.includes(data.status)?data.status:'unknown';
      services=Object.fromEntries(Object.keys(labels).map(key=>[key,allowed.includes(data.services?.[key])?data.services[key]:'unknown']));}
  } catch { services.api='unavailable'; }
  return <section className="page-hero"><div className="container narrow"><SectionHeading eyebrow="Service status" title={`Platform: ${overall}`} body="Read-only checks of the running backend. Unknown means a dependency has not been verified."/>
    <div className="status-list">{Object.entries(labels).map(([key,label])=><div key={key}><b>{label}</b><span className="status-pill">{services[key]}</span></div>)}</div>
    <p>Storage readiness does not guarantee persistence. Notification configuration does not prove delivery. No email is sent by these checks.</p></div></section>;
}

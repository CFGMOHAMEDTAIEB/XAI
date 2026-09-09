export const serviceLabels={api:'API',identity:'Database connectivity',compression:'Compression prerequisites',storage:'Storage readiness',notifications:'Notifications',security_scanner:'Security scanner readiness'};
const allowed=new Set(['operational','degraded','unavailable','unknown']);
export function normalizeStatus(data){
 const services=Object.fromEntries(Object.keys(serviceLabels).map(key=>[key,allowed.has(data?.services?.[key])?data.services[key]:'unknown']));
 const values=Object.values(services);
 const overall=values.includes('unavailable')||values.includes('degraded')?'degraded':values.includes('unknown')?'unknown':'operational';
 return {overall,services};
}

import {apiUrl,portalUrl} from '@/lib/deployment';
export const metadata={title:'Protected share',robots:{index:false,follow:false}};
export default async function SharePage({params}:{params:Promise<{code:string}>}){
 const {code}=await params;
 let available=false;
 try{
  const response=await fetch(`${apiUrl}/public/shares/${encodeURIComponent(code)}`,{cache:'no-store',signal:AbortSignal.timeout(10000)});
  available=response.ok;
 }catch{/* Availability remains unverified. */}
 return <section className="page-hero"><div className="container narrow"><h1>{available?'Protected share':'Share unavailable'}</h1><p>{available?'Sign in as the intended recipient and enter your share code in the portal inbox. File details require authorization.':'The share could not be verified. It may be invalid, expired, exhausted, or the backend may be unavailable.'}</p><a className="button" href={`${portalUrl}/inbox`}>Open portal inbox</a></div></section>;
}

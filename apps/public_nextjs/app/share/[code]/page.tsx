import {apiUrl} from '@/lib/deployment';
type ShareInfo={file_name:string;original_size:number;compressed_size:number;codec:string;expires_at:string;authentication_required:boolean};

export default async function SharePage({params}:{params:Promise<{code:string}>}){
  const {code}=await params;
  const api=apiUrl;
  const response=await fetch(`${api}/public/shares/${encodeURIComponent(code)}`,{cache:'no-store',signal:AbortSignal.timeout(10000)});
  if(!response.ok)return <main><h1>Share unavailable</h1><p>The code is invalid, expired, or exhausted.</p></main>;
  const share=await response.json() as ShareInfo;
  return <main><h1>{share.file_name}</h1><p>Compressed with {share.codec}.</p><p>{share.original_size.toLocaleString()} bytes → {share.compressed_size.toLocaleString()} bytes</p><p>Expires {new Date(share.expires_at).toLocaleString()}.</p><p>Sign in to the XAI application to redeem and download this protected share.</p></main>;
}

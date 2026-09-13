import {siteUrl} from '@/lib/deployment';import type{MetadataRoute}from'next';
export default function sitemap():MetadataRoute.Sitemap{return['','security','architecture','downloads','pricing','docs','contact','privacy','terms'].map(x=>({url:`${siteUrl}/${x}`}))}

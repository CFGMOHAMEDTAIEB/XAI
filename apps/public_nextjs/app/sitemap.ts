import {siteUrl} from '@/lib/deployment';
import type{MetadataRoute}from'next';export default function sitemap():MetadataRoute.Sitemap{const base=siteUrl;return['','security','architecture','downloads','pricing','docs','status','contact','privacy','terms'].map(x=>({url:`${base}/${x}`,lastModified:new Date()}))}

export type ProductionRelease={platform:string;version:string;filename:string;architecture:string;releaseNotes:string;sha256:string;sizeBytes:number;releasedAt:string;url:string;channel:'PRODUCTION';signing:'VERIFIED';installTest:'PASSED'};
export function productionReleases(manifest:unknown):ProductionRelease[];

"""Validate and export the accepted 140-file Hybrid V3 benchmark without rewriting it."""
import csv,json,statistics,sys
from collections import Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'engines/XAI-Compress/results/hybrid_v3'
OUT=ROOT/'reports/benchmark'
METHODS=('hybrid_v1','hybrid_v2','hybrid_v3_top3','brotli-11')
def number(row,name):return float(row[name])
def main():
    summary=json.loads((SOURCE/'benchmark_summary.json').read_text(encoding='utf-8'))
    rows=list(csv.DictReader((SOURCE/'benchmark.csv').open(encoding='utf-8-sig',newline='')))
    selected=[row for row in rows if row['method'] in METHODS]
    counts=Counter(row['method'] for row in selected)
    if summary.get('status')!='ACCEPTED' or summary.get('common_source_count')!=140:raise SystemExit('Authoritative benchmark acceptance metadata is invalid')
    if any(counts[m]<140 for m in METHODS):raise SystemExit(f'Incomplete benchmark methods: {dict(counts)}')
    if any(row.get('roundtrip_sha_pass','').lower()!='true' for row in selected):raise SystemExit('A selected benchmark row lacks SHA-256 round-trip evidence')
    OUT.mkdir(parents=True,exist_ok=True)
    fields=['source_id','original_bytes','compressed_bytes','BPB','compression_seconds','decompression_seconds','compression_mib_s','decompression_mib_s','codec','route','sha256_match','category','size_bucket','repetition']
    with (OUT/'latest_results.csv').open('w',encoding='utf-8',newline='') as handle:
        writer=csv.DictWriter(handle,fieldnames=fields);writer.writeheader()
        for row in selected:writer.writerow({'source_id':row['source_id'],'original_bytes':row['original_bytes'],'compressed_bytes':row['compressed_bytes'],'BPB':row['actual_bpb'],'compression_seconds':number(row,'compression_ms')/1000,'decompression_seconds':number(row,'decompression_ms')/1000,'compression_mib_s':row['compression_MiB_s'],'decompression_mib_s':row['decompression_MiB_s'],'codec':row['method'],'route':row.get('selected_strategy',''),'sha256_match':row['roundtrip_sha_pass'],'category':row.get('category',''),'size_bucket':row.get('size_bucket',''),'repetition':row.get('repetition','')})
    result={'source':'engines/XAI-Compress/results/hybrid_v3','benchmark_version':summary['benchmark_version'],'status':summary['status'],'files':summary['common_source_count'],'original_bytes':summary['common_original_bytes'],'methods':{},'limitations':summary['repetition_policy']}
    for method in METHODS:
        records=[r for r in selected if r['method']==method]
        first_reps=[r for r in records if r.get('repetition','0')=='0'] or records
        result['methods'][method]={'rows':len(records),'unique_sources':len({r['source_id'] for r in records}),'compressed_bytes':summary['methods'][method]['compressed_bytes'],'weighted_bpb':summary['methods'][method]['weighted_bpb'],'compression_mib_s':summary['methods'][method]['compression_MiB_s'],'decompression_mib_s':summary['methods'][method]['decompression_MiB_s'],'median_file_bpb':statistics.median(number(r,'actual_bpb') for r in first_reps),'round_trip_success_rate':sum(r['roundtrip_sha_pass'].lower()=='true' for r in records)/len(records)}
    (OUT/'latest_summary.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({'status':'PASS','output':str(OUT),'rows':len(selected),'methods':dict(counts)}))
if __name__=='__main__':sys.exit(main())

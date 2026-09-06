import {Component,signal} from '@angular/core';
import {FormsModule} from '@angular/forms';
import {saveBlob} from '../core/download';
import {ApiService} from '../core/api.service';

@Component({standalone:true,imports:[FormsModule],template:`<div class="heading"><div><h1>Compress</h1><p>Create a verified lossless artifact.</p></div></div><article class="panel form-panel"><label class="drop">@if(file()){<b>{{file()?.name}}</b><span>{{file()?.size}} bytes</span>}@else{<b>Choose a file</b><span>The backend uses Hybrid V3 with frozen Selector V2/top-3 routing.</span>}<input type="file" (change)="pick($event)"></label><label>Compression mode<select [(ngModel)]="mode"><option value="hybrid-v3">Hybrid V3 (Top-3)</option></select></label><p>SHA-256 round-trip verification is required for every job.</p><button class="primary" [disabled]="!file()||running()" (click)="start()">{{running()?'Processing...':'Start compression'}}</button>@if(jobId()){<p>File ID: {{jobId()}}</p><button (click)="download()">Download .xaic</button>}@if(message()){<div class="notice">{{message()}}</div>}</article>`})
export class CompressPage{
  file=signal<File|null>(null);running=signal(false);message=signal('');mode='hybrid-v3';integrity=true;jobId=signal<number|null>(null);artifactName='';
  constructor(private api:ApiService){}
  pick(e:Event){this.file.set((e.target as HTMLInputElement).files?.[0]??null)}
  download(){const id=this.jobId();if(id)this.api.download(id).subscribe({next:b=>saveBlob(b,this.artifactName),error:()=>this.message.set('Download failed.')})}
  start(){const selected=this.file();if(!selected)return;this.running.set(true);this.message.set('');this.jobId.set(null);this.api.compress(selected).subscribe({next:(result)=>{this.jobId.set((result as {id:number}).id);this.artifactName=selected.name+'.xaic';this.running.set(false);this.message.set('Compression completed and SHA-256 round-trip verified.')},error:e=>{this.running.set(false);this.message.set(e?.error?.detail??'Compression failed.')}})}
}

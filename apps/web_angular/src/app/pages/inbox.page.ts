import {Component,signal} from '@angular/core';
import {FormsModule} from '@angular/forms';
import {JsonPipe} from '@angular/common';
import {ApiService} from '../core/api.service';
import {saveBlob} from '../core/download';
@Component({standalone:true,imports:[FormsModule,JsonPipe],template:`
<div class="heading"><div><h1>Inbox</h1><p>Import an attachment saved from your email, including unknown senders.</p></div></div>
<article class="panel form-panel"><label>Received XAI attachment<input type="file" accept=".xaic" (change)="pick($event)"></label>
<p>XAI validates the container, size limits and checksums before returning the restored file.</p>
<button class="primary" [disabled]="!file||busy()" (click)="restore()">{{busy()?'Validating and decompressing...':'Decompress attachment'}}</button>
@if(message()){<p>{{message()}}</p>}</article>
<article class="panel form-panel"><label>Share code<input [(ngModel)]="code" placeholder="XC-ABCD-EFGH-IJKL"></label><button class="primary" [disabled]="!code" (click)="redeem()">Redeem</button>@if(result()){<pre>{{result()|json}}</pre>}</article>`})
export class InboxPage{
  code='';file:File|null=null;busy=signal(false);message=signal('');result=signal<unknown>(null);
  constructor(private api:ApiService){}
  pick(event:Event){this.file=(event.target as HTMLInputElement).files?.[0]??null;this.message.set('')}
  restore(){if(!this.file)return;const file=this.file;this.busy.set(true);this.message.set('');
    this.api.decompress(file).subscribe({next:b=>{saveBlob(b,file.name.replace(/\.xaic$/i,'')||'restored.bin');this.busy.set(false);this.message.set('Container integrity verified. Restored file downloaded.')},error:async e=>{this.busy.set(false);let detail='Attachment validation or decompression failed.';if(e.error instanceof Blob){try{detail=JSON.parse(await e.error.text()).detail??detail}catch{}}this.message.set(detail)}})}
  redeem(){this.api.redeem(this.code).subscribe({next:x=>this.result.set(x),error:e=>this.result.set({error:e?.error?.detail??'Backend unavailable'})})}
}

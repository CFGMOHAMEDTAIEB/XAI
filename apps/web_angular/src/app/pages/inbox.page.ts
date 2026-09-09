import {Component,signal} from '@angular/core';
import {FormsModule} from '@angular/forms';
import {ApiService} from '../core/api.service';
import {saveBlob} from '../core/download';
@Component({standalone:true,imports:[FormsModule],template:`
<div class="heading"><div><h1>Inbox</h1><p>Decompress an XAI attachment or download a shared artifact.</p></div></div>
<article class="panel form-panel"><label>Received XAI attachment<input type="file" accept=".xaic" [disabled]="busy()" (change)="pick($event)"></label><button class="primary" [disabled]="!file||busy()" (click)="restore()">Decompress attachment</button></article>
<article class="panel form-panel"><label>Share code<input [(ngModel)]="code" [disabled]="busy()" (ngModelChange)="available.set(false)"></label><button class="primary" [disabled]="!code||busy()" (click)="redeem()">Redeem</button>@if(available()){<button [disabled]="busy()" (click)="downloadShare()">Download shared artifact</button>}</article>
@if(busy()){<p>Processing...</p>}@if(message()){<p role="status">{{message()}}</p>}`})
export class InboxPage {
 code='';file:File|null=null;busy=signal(false);message=signal('');available=signal(false);
 constructor(private api:ApiService){}
 pick(e:Event){this.file=(e.target as HTMLInputElement).files?.[0]??null;this.message.set('')}
 restore(){if(!this.file||this.busy())return;const file=this.file;this.busy.set(true);this.api.decompress(file).subscribe({next:b=>{this.busy.set(false);saveBlob(b,file.name.replace(/\.xaic$/i,'')||'restored.bin');this.message.set('Integrity verified. Restored file downloaded.')},error:()=>this.fail('Validation or decompression failed. Check the file and service status.')})}
 downloadShare(){if(this.busy())return;this.busy.set(true);this.api.downloadShare(this.code).subscribe({next:b=>{this.busy.set(false);saveBlob(b,'shared.xaic');this.available.set(false);this.message.set('Shared artifact downloaded.')},error:()=>this.fail('Shared artifact unavailable or download limit reached.')})}
 redeem(){if(this.busy())return;this.busy.set(true);this.available.set(false);this.api.redeem(this.code).subscribe({next:()=>{this.busy.set(false);this.available.set(true);this.message.set('Share available. Download the artifact.')},error:()=>this.fail('Share unavailable. Check the code and signed-in recipient account.')})}
 private fail(message:string){this.busy.set(false);this.message.set(message)}
}

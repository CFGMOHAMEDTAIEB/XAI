import {Component,signal} from '@angular/core';
import {FormsModule} from '@angular/forms';
import {ApiService} from '../core/api.service';
@Component({standalone:true,imports:[FormsModule],template:`<div class="heading"><div><h1>Secure sharing</h1><p>Create a temporary recipient-bound code.</p></div></div><article class="panel form-panel"><label>File ID<input type="number" [(ngModel)]="fileId"></label><label>Recipient email<input type="email" [(ngModel)]="email"></label><button class="primary" [disabled]="busy()||!fileId||!email" (click)="create()">Create code</button><button class="primary" [disabled]="busy()||!fileId||!email" (click)="send()">Email compressed attachment</button><p>Attachment email availability depends on the provider. If unavailable, create a secure share code.</p>@if(message()){<p role="status">{{message()}}</p>}@if(code()){<div class="code"><small>Share code</small><strong>{{code()}}</strong></div>}</article>`})
export class SharesPage {
 fileId:number|null=null;email='';code=signal('');message=signal('');busy=signal(false);
 constructor(private api:ApiService){}
 send(){if(this.busy()||!this.fileId)return;this.busy.set(true);this.message.set('Sending...');this.api.email(this.fileId,this.email).subscribe({next:()=>{this.busy.set(false);this.message.set('Email provider accepted the attachment. Receipt is not yet confirmed.')},error:()=>{this.busy.set(false);this.message.set('Attachment email unavailable. Use a secure share code or retry later.')}})}
 create(){if(this.busy()||!this.fileId)return;this.busy.set(true);this.code.set('');this.message.set('');this.api.share(this.fileId,this.email).subscribe({next:x=>{this.busy.set(false);this.code.set(x.share_code)},error:()=>{this.busy.set(false);this.message.set('Could not create a share. Check the file ID and recipient, then retry.')}})}
}

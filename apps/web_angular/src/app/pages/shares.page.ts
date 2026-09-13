import {DatePipe} from '@angular/common';
import {Component,signal} from '@angular/core';
import {FormsModule} from '@angular/forms';
import {forkJoin} from 'rxjs';
import {ApiService} from '../core/api.service';
import {FileItem,ShareItem} from '../models/models';
import {IconComponent} from '../ui/icon.component';

@Component({standalone:true,imports:[FormsModule,DatePipe,IconComponent],template:`
<div class="heading"><div><p class="eyebrow">Recipient-bound access</p><h1>Secure sharing</h1><p>Create and manage time-limited access to your verified artifacts.</p></div><button class="outline" [disabled]="loading()" (click)="load()"><x-icon name="refresh"/>Refresh</button></div>
<div class="columns share-columns">
 <article class="panel form-panel">
  <div class="card-title"><x-icon name="share"/><div><h2>Create a secure share</h2><p class="muted">The recipient must sign in with the email you specify.</p></div></div>
  <label>File<select [(ngModel)]="fileId" [disabled]="busy()||loading()"><option [ngValue]="null">Choose a completed file</option>@for(file of files();track file.id){<option [ngValue]="file.id">{{file.name}}</option>}</select></label>
  @if(!loading()&&!files().length){<div class="notice">No completed artifacts are available to share yet.</div>}
  <label>Recipient email<input type="email" [(ngModel)]="email" autocomplete="email" placeholder="recipient@example.com" [disabled]="busy()"></label>
  <button class="primary" [disabled]="busy()||!fileId||!validEmail()" (click)="create()"><x-icon name="share"/>{{busyAction()==='create'?'Creating…':'Create one-hour share'}}</button>
  @if(emailSupported()){
   <button class="secondary" [disabled]="busy()||!fileId||!validEmail()" (click)="send()"><x-icon name="mail"/>{{busyAction()==='email'?'Sending…':'Email compressed attachment'}}</button>
  }@else{<p class="muted">Compressed attachment email is unavailable with the configured provider. Secure share codes remain available.</p>}
  @if(message()){<div [class.error]="messageType()==='error'" [class.success-banner]="messageType()==='success'" role="status">{{message()}}</div>}
  @if(code()){<div class="result-card"><div><x-icon name="check"/><b>Share created</b></div><p>Send this one-time code only to the intended recipient. It expires at {{createdExpiry()|date:'medium'}}.</p><div class="code"><small>Share code</small><strong>{{code()}}</strong></div><button class="outline" (click)="copyCode()">{{copied()?'Copied':'Copy code'}}</button></div>}
 </article>
 <article class="panel">
  <div class="panel-header"><div><h2>Your shares</h2><p class="muted">Codes are shown only once when created.</p></div></div>
  @if(loading()){<div class="skeleton" role="status"><span></span><span></span><span></span></div>}
  @else if(!shares().length){<div class="empty-state"><x-icon name="share"/><h3>No shares yet</h3><p>Your active and past shares will appear here.</p></div>}
  @else{<div class="share-list">@for(share of shares();track share.id){<div class="share-row"><div><b>{{share.file_name}}</b><small>{{share.recipient_email}}</small></div><span class="badge" [class.success]="share.status==='active'" [class.danger]="share.status==='revoked'||share.status==='expired'">{{share.status}}</span><div><small>Expires</small><time>{{share.expires_at|date:'medium'}}</time></div><div><small>Downloads</small><span>{{share.download_count}} / {{share.max_downloads}}</span></div>@if(share.status==='active'){<button class="danger" [disabled]="busy()" (click)="revoke(share)">Revoke</button>}</div>}</div>}
 </article>
</div>`})
export class SharesPage {
 fileId:number|null=null;email='';files=signal<FileItem[]>([]);shares=signal<ShareItem[]>([]);code=signal('');createdExpiry=signal('');message=signal('');messageType=signal<'success'|'error'>('success');loading=signal(false);busyAction=signal<''|'create'|'email'|'revoke'>('');emailSupported=signal(false);copied=signal(false);
 constructor(private api:ApiService){this.load()}
 busy(){return this.busyAction()!==''}
 validEmail(){return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(this.email.trim())}
 load(){if(this.loading())return;this.loading.set(true);this.message.set('');forkJoin({files:this.api.files(),shares:this.api.shares(),email:this.api.emailCapabilities()}).subscribe({next:value=>{this.files.set(value.files.filter(file=>file.status==='completed'));this.shares.set(value.shares);this.emailSupported.set(value.email.artifact_email_supported);this.loading.set(false)},error:()=>{this.loading.set(false);this.fail('Sharing information is unavailable right now.')}})}
 create(){if(this.busy()||!this.fileId||!this.validEmail())return;this.busyAction.set('create');this.code.set('');this.message.set('');this.api.share(this.fileId,this.email.trim()).subscribe({next:value=>{this.busyAction.set('');this.code.set(value.share_code);this.createdExpiry.set(value.expires_at);this.messageType.set('success');this.message.set('Secure share created.');this.loadShares()},error:()=>{this.busyAction.set('');this.fail('Could not create the share. Confirm that you own the selected file and try again.')}})}
 send(){if(this.busy()||!this.fileId||!this.validEmail()||!this.emailSupported())return;this.busyAction.set('email');this.message.set('');this.api.email(this.fileId,this.email.trim()).subscribe({next:()=>{this.busyAction.set('');this.messageType.set('success');this.message.set('The email provider accepted the attachment. Inbox delivery is not confirmed.')},error:()=>{this.busyAction.set('');this.fail('The provider did not accept the attachment. Use a secure share code or try again later.')}})}
 revoke(share:ShareItem){if(this.busy())return;this.busyAction.set('revoke');this.api.revokeShare(share.id).subscribe({next:()=>{this.busyAction.set('');this.messageType.set('success');this.message.set('Share revoked.');this.loadShares()},error:()=>{this.busyAction.set('');this.fail('The share could not be revoked. Refresh and try again.')}})}
 async copyCode(){try{await navigator.clipboard.writeText(this.code());this.copied.set(true);setTimeout(()=>this.copied.set(false),1800)}catch{this.fail('Copy is unavailable. Select the code and copy it manually.')}}
 private loadShares(){this.api.shares().subscribe({next:value=>this.shares.set(value),error:()=>this.fail('The share was created, but the list could not be refreshed.')})}
 private fail(value:string){this.messageType.set('error');this.message.set(value)}
}

import {DatePipe} from '@angular/common';
import {HttpErrorResponse} from '@angular/common/http';
import {Component,signal} from '@angular/core';
import {FormsModule} from '@angular/forms';
import {forkJoin} from 'rxjs';
import {ApiService} from '../core/api.service';
import {saveBlob} from '../core/download';
import {FileItem,RedeemedShare,ShareItem,ShareResult} from '../models/models';
import {IconComponent} from '../ui/icon.component';

@Component({standalone:true,imports:[FormsModule,DatePipe,IconComponent],template:`
<div class="heading"><div><p class="eyebrow">Recipient-bound access</p><h1>Secure sharing</h1><p>Create a protected share or receive a file someone shared with you.</p></div><button class="outline" [disabled]="loading()" (click)="load()"><x-icon name="refresh"/>Refresh</button></div>
<div class="columns share-columns">
 <article class="panel form-panel">
  <div class="card-title"><x-icon name="share"/><div><h2>Share a file</h2><p class="muted">The recipient must sign in with the email you specify.</p></div></div>
  <label>File<select [(ngModel)]="fileId" [disabled]="busy()||loading()"><option [ngValue]="null">Select a completed file</option>@for(file of files();track file.id){<option [ngValue]="file.id">{{file.name}}</option>}</select></label>
  @if(!loading()&&!files().length){<div class="notice">No completed artifacts are available to share yet.</div>}
  <label>Recipient email<input type="email" [(ngModel)]="email" autocomplete="email" placeholder="recipient@example.com" [disabled]="busy()"></label>
  <label>Expiration<select [(ngModel)]="expiresMinutes" [disabled]="busy()"><option [ngValue]="15">15 minutes</option><option [ngValue]="60">1 hour</option><option [ngValue]="1440">1 day</option><option [ngValue]="10080">7 days</option></select></label>
  <button class="primary" [disabled]="busy()||!fileId||!validEmail()||!expiresMinutes" (click)="create()"><x-icon name="share"/>{{busyAction()==='create'?'Creating…':'Create share'}}</button>
  @if(message()){<div [class.error]="messageType()==='error'" [class.success-banner]="messageType()==='success'" role="status">{{message()}}</div>}
  @if(code()){<div class="result-card"><div><x-icon name="check"/><b>Share created successfully</b></div><p><b>File:</b> {{createdFile()}}</p><p><b>Recipient:</b> {{createdRecipient()}}</p><div class="code"><small>Share code</small><strong>{{code()}}</strong></div><p><b>Expires:</b> {{createdExpiry()|date:'medium'}}</p><p><b>Email:</b> {{emailStatusLabel(createdDelivery())}}</p><button class="outline" (click)="copyCode()">{{copied()?'Copied':'Copy code'}}</button></div>}
 </article>
 <article class="panel form-panel">
  <div class="card-title"><x-icon name="download"/><div><h2>Receive a file</h2><p class="muted">Someone shared a file with you. Enter the code you received by email to access it.</p></div></div>
  <label>Share code<input [(ngModel)]="redeemCode" (ngModelChange)="clearReceived()" [disabled]="busy()" autocomplete="off" spellcheck="false" placeholder="XC-XXXX-XXXX-XXXX"></label>
  <button class="secondary" [disabled]="busy()||redeemCode.trim().length<8" (click)="redeem()">{{busyAction()==='redeem'?'Checking…':'Receive file'}}</button>
  @if(receiveMessage()){<div [class.error]="!received()" role="alert">{{receiveMessage()}}</div>}
  @if(received();as share){<div class="result-card"><div><x-icon name="file"/><b>Shared file ready</b></div><p><b>Filename:</b> {{share.file.name}}</p><p><b>Size:</b> {{formatBytes(share.file.size)}}</p>@if(share.sender){<p><b>Sender:</b> {{share.sender.name}} ({{share.sender.email}})</p>}<p><b>Expires:</b> {{share.expires_at|date:'medium'}}</p><p><b>Downloads remaining:</b> {{share.remaining_downloads}} / {{share.max_downloads}}</p><button class="primary" [disabled]="busy()||share.remaining_downloads<1" (click)="downloadReceived()"><x-icon name="download"/>{{busyAction()==='download'?'Downloading…':'Download'}}</button></div>}
 </article>
</div>
<article class="panel">
 <div class="panel-header"><div><h2>Your shares</h2><p class="muted">Codes are shown only once when created.</p></div></div>
 @if(loading()){<div class="skeleton" role="status"><span></span><span></span><span></span></div>}
 @else if(!shares().length){<div class="empty-state"><x-icon name="share"/><h3>No shares yet</h3><p>Your active and past shares will appear here.</p></div>}
 @else{<div class="share-list">@for(share of shares();track share.id){<div class="share-row"><div><b>{{share.file_name}}</b><small>{{share.recipient_email}}</small></div><span class="badge" [class.success]="share.status==='active'" [class.danger]="share.status==='revoked'||share.status==='expired'">{{statusLabel(share.status)}}</span><div><small>Expires</small><time>{{share.expires_at|date:'medium'}}</time></div><div><small>Downloads</small><span>{{share.download_count}} / {{share.max_downloads}}</span></div>@if(share.status==='active'){<button class="danger" [disabled]="busy()" (click)="revoke(share)">Revoke</button>}</div>}</div>}
</article>`})
export class SharesPage {
 fileId:number|null=null;email='';expiresMinutes=60;redeemCode='';files=signal<FileItem[]>([]);shares=signal<ShareItem[]>([]);code=signal('');createdFile=signal('');createdRecipient=signal('');createdExpiry=signal('');createdDelivery=signal<ShareResult['email_delivery']>('not_configured');message=signal('');messageType=signal<'success'|'error'>('success');receiveMessage=signal('');received=signal<RedeemedShare|null>(null);loading=signal(false);busyAction=signal<''|'create'|'redeem'|'download'|'revoke'>('');copied=signal(false);
 constructor(private api:ApiService){this.load()}
 busy(){return this.busyAction()!==''}
 validEmail(){return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(this.email.trim())}
 formatBytes(value:number){if(value<1024)return value+' B';if(value<1048576)return (value/1024).toFixed(1)+' KiB';return (value/1048576).toFixed(1)+' MiB'}
 statusLabel(status:ShareItem['status']){return status==='active'?'Active':status==='expired'?'Expired':status==='exhausted'?'Exhausted':'Revoked'}
 emailStatusLabel(status:ShareResult['email_delivery']){return status==='captured_by_mailpit'?'Captured by Mailpit (local/demo environment)':status==='accepted_by_provider'||status==='accepted_by_smtp'?'Accepted by provider':status==='failed'?'Delivery failed':'Email service not configured'}
 load(){if(this.loading())return;this.loading.set(true);forkJoin({files:this.api.files(),shares:this.api.shares()}).subscribe({next:value=>{this.files.set(value.files.filter(file=>file.status==='completed'));this.shares.set(value.shares);this.loading.set(false)},error:()=>{this.loading.set(false);this.fail('Sharing information is unavailable right now.')}})}
 create(){if(this.busy()||!this.fileId||!this.validEmail()||!this.expiresMinutes)return;const selected=this.files().find(file=>file.id===this.fileId);this.busyAction.set('create');this.code.set('');this.message.set('');this.api.share(this.fileId,this.email.trim(),this.expiresMinutes).subscribe({next:value=>{this.busyAction.set('');this.code.set(value.share_code);this.createdFile.set(selected?.name||'Selected file');this.createdRecipient.set(value.recipient_email);this.createdExpiry.set(value.expires_at);this.createdDelivery.set(value.email_delivery);this.messageType.set(value.email_delivery==='failed'?'error':'success');this.message.set(value.email_delivery==='captured_by_mailpit'?'Share created. The notification was captured by Mailpit.':value.email_delivery==='accepted_by_provider'||value.email_delivery==='accepted_by_smtp'?'Share created. The email provider accepted the notification.':value.email_delivery==='failed'?'Share created, but notification delivery failed. Copy the code for the recipient.':'Share created. Email is not configured, so copy the code for the recipient.');this.loadShares()},error:()=>{this.busyAction.set('');this.fail('Could not create the share. Confirm the file, recipient, and expiration, then try again.')}})}
 redeem(){const code=this.redeemCode.trim();if(this.busy()||code.length<8)return;this.busyAction.set('redeem');this.received.set(null);this.receiveMessage.set('');this.api.redeem(code).subscribe({next:value=>{this.busyAction.set('');this.received.set(value);this.receiveMessage.set('')},error:(error:HttpErrorResponse)=>{this.busyAction.set('');this.receiveMessage.set(this.redeemError(error))}})}
 downloadReceived(){const share=this.received();const code=this.redeemCode.trim();if(!share||this.busy())return;this.busyAction.set('download');this.receiveMessage.set('');this.api.downloadShare(code).subscribe({next:blob=>{saveBlob(blob,share.file.name);this.busyAction.set('');this.received.set({...share,remaining_downloads:Math.max(0,share.remaining_downloads-1)});this.receiveMessage.set('Download complete.')},error:(error:HttpErrorResponse)=>{this.busyAction.set('');this.receiveMessage.set(this.redeemError(error))}})}
 clearReceived(){this.received.set(null);this.receiveMessage.set('')}
 revoke(share:ShareItem){if(this.busy())return;this.busyAction.set('revoke');this.api.revokeShare(share.id).subscribe({next:()=>{this.busyAction.set('');this.messageType.set('success');this.message.set('Share revoked.');this.loadShares()},error:()=>{this.busyAction.set('');this.fail('The share could not be revoked. Refresh and try again.')}})}
 async copyCode(){try{await navigator.clipboard.writeText(this.code());this.copied.set(true);setTimeout(()=>this.copied.set(false),1800)}catch{this.fail('Copy is unavailable. Select the code and copy it manually.')}}
 private redeemError(error:HttpErrorResponse){return error.status===410?'This share has expired.':error.status===409?'This share has no downloads remaining.':error.status===403?'This share is not authorized for your account.':error.status===404?'This share code is invalid or no longer available.':'The share could not be checked right now. Please try again.'}
 private loadShares(){this.api.shares().subscribe({next:value=>this.shares.set(value),error:()=>this.fail('The share was created, but the list could not be refreshed.')})}
 private fail(value:string){this.messageType.set('error');this.message.set(value)}
}

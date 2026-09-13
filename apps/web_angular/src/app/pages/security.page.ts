import {Component,OnDestroy,signal} from '@angular/core';
import {FormsModule} from '@angular/forms';
import {HttpErrorResponse} from '@angular/common/http';
import {firstValueFrom} from 'rxjs';
import {ApiService} from '../core/api.service';
import {IconComponent} from '../ui/icon.component';
import {DatePipe} from '@angular/common';

@Component({standalone:true,imports:[FormsModule,IconComponent,DatePipe],template:`
<div class="heading"><div><h1>Security</h1><p>Protect your account and review authenticator access.</p></div></div>
<article class="panel"><div class="card-title"><x-icon name="mail"/><div><h2>Account verification</h2><p class="muted">Your verified contact methods.</p></div></div>
 <p><strong>Email</strong> {{profile()?.email||'—'}} <span class="status-pill" [class.active]="profile()?.email_verified">{{profile()?.email_verified?'Verified':'Not verified'}}</span></p>
 <p><strong>Phone</strong> {{profile()?.phone_number||'Not provided'}} <span class="status-pill" [class.active]="profile()?.phone_verified">{{profile()?.phone_verified?'Verified':'Not verified'}}</span></p>
</article>
<article class="panel security-card" aria-labelledby="authenticator-title">
 <div class="security-summary"><div class="security-icon" aria-hidden="true"><x-icon name="security"/></div><div><p class="eyebrow">Account protection</p><h2 id="authenticator-title">XAI Authenticator</h2><p class="muted">Use time-based codes generated securely by the XAI mobile app.</p></div><span class="status-pill" [class.active]="state()==='enabled'">{{statusLabel()}}</span></div>

 @if(state()==='loading'){<p role="status">Checking authenticator status…</p>}
 @if(state()==='not_configured'||state()==='expired'||state()==='awaiting_email'||state()==='awaiting_totp'){
  <div class="security-actions"><button class="primary" [disabled]="busy()" (click)="start()">{{state()==='not_configured'?'Set up authenticator':'Restart setup'}}</button></div>
 }
 @if(state()==='pending_activation'){
  <section class="enrollment" aria-labelledby="setup-title">
   <div class="step-marker">1</div><div><h3 id="setup-title">Set up XAI Authenticator</h3><ol><li>Open XAI on your phone.</li><li>Tap <strong>Add account</strong>.</li><li>Scan this QR code.</li></ol></div>
   <div class="qr-frame"><img [src]="qr()" width="240" height="240" alt="QR code for XAI Authenticator enrollment"></div>
   <p class="muted centered">This authorized QR expires in {{expiresMinutes()}} minutes.</p>
   <details><summary>Can't scan the QR code?</summary><p>Enter this setup URI manually in a trusted authenticator. Keep it private.</p><code class="setup-uri">{{uri()}}</code></details>
   <div class="verification-block"><div class="step-marker">2</div><div><h3>Verify enrollment</h3><p>Enter the 6-digit code from XAI Authenticator.</p></div>
    <label class="sr-only" for="enrollment-code">6-digit code from XAI Authenticator</label>
    <input id="enrollment-code" class="otp-input" [(ngModel)]="code" inputmode="numeric" pattern="[0-9]{6}" maxlength="6" autocomplete="one-time-code" [disabled]="busy()" (input)="digitsOnly()">
    <button class="primary" [disabled]="busy()||!validCode(code)" (click)="confirm()">{{busy()?'Verifying…':'Verify and enable'}}</button>
   </div>
  </section>
 }
 @if(state()==='enabled'){
  <div class="success-banner" role="status"><strong>XAI Authenticator is now protecting your account.</strong><span>Future sign-ins require a current code from your authenticator.</span></div>
  <div class="security-actions"><button class="secondary" (click)="showManagement.set(!showManagement())">Manage authenticator</button><button class="secondary" (click)="showRecovery.set(!showRecovery())">Recovery options</button></div>
  @if(showManagement()){<section class="subpanel"><h3>Registered devices</h3>@if(devicesLoading()){<p role="status">Loading devices…</p>}@else if(!devices().length){<div class="empty-state compact"><x-icon name="security"/><h3>No authenticator device registered</h3><p>Device-bound approvals will appear here after registration.</p></div>}@else{<div class="device-list">@for(device of devices();track device.device_id){<div class="device-row"><x-icon name="security"/><div><b>{{device.platform}} · {{device.app_version}}</b><small>Last activity {{device.last_activity|date:'medium'}}</small></div><span class="badge" [class.success]="device.status==='active'">{{device.status}}</span>@if(device.status==='active'){<button class="danger" [disabled]="busy()" (click)="revokeDevice(device.device_id)">Revoke</button>}</div>}</div>}</section>}
  @if(showRecovery()){<section class="subpanel"><h3>Recovery options</h3><p>Generating new recovery codes replaces all prior codes. For safety, this action is available through the authenticated recovery endpoint but is not triggered merely by opening this panel.</p><button class="danger" [disabled]="busy()" (click)="generateRecovery()">Generate new recovery codes</button>@if(recovery().length){<div class="notice" role="status"><strong>Save these codes now. They are shown once.</strong><div class="recovery-grid">@for(item of recovery();track item){<code>{{item}}</code>}</div></div>}</section>}
 }
 @if(message()){<div class="error" role="alert">{{message()}}</div>}
</article>
<article class="panel"><div class="card-title"><x-icon name="key"/><div><h2>Password and sessions</h2><p class="muted">Use the verified reset flow to change your password.</p></div></div><a class="outline" href="/forgot-password">Change password</a></article>`})
export class SecurityPage implements OnDestroy {
 state=signal('loading');profile=signal<{email:string;phone_number:string|null;email_verified:boolean;phone_verified:boolean}|null>(null);qr=signal('');uri=signal('');message=signal('');busy=signal(false);showManagement=signal(false);showRecovery=signal(false);devices=signal<Array<{device_id:string;platform:string;app_version:string;status:string;registered_at:string;last_activity:string}>>([]);devicesLoading=signal(false);recovery=signal<string[]>([]);code='';enrollmentId='';expiresSeconds=600;destroyed=false;
 constructor(private api:ApiService){void this.refresh();firstValueFrom(this.api.me()).then(value=>this.profile.set(value)).catch(()=>{});this.loadDevices()}
 statusLabel(){return this.state()==='enabled'?'Active':this.state()==='pending_activation'||this.state().startsWith('awaiting_')?'Pending':'Not configured'}
 expiresMinutes(){return Math.max(1,Math.ceil(this.expiresSeconds/60))}
 validCode(value:string){return /^\d{6}$/.test(value)}
 digitsOnly(){this.code=this.code.replace(/\D/g,'').slice(0,6)}
 async run(action:()=>Promise<void>){if(this.busy())return;this.busy.set(true);this.message.set('');try{await action()}catch(error){if(!this.destroyed)this.message.set(this.safeError(error))}finally{if(!this.destroyed)this.busy.set(false)}}
 refresh(){return this.run(async()=>{const status=await firstValueFrom(this.api.totpStatus());if(!this.destroyed)this.state.set(status.state)})}
 start(){return this.run(async()=>{const value=await firstValueFrom(this.api.startAuthenticator());if(this.destroyed)return;if(!value.enrollment_id||!value.qr_data_uri?.startsWith('data:image/png;base64,')||!value.otpauth_uri?.startsWith('otpauth://'))throw new Error('malformed');this.enrollmentId=value.enrollment_id;this.expiresSeconds=value.expires_in_seconds;this.qr.set(value.qr_data_uri);this.uri.set(value.otpauth_uri);this.state.set('pending_activation')})}
 confirm(){return this.run(async()=>{const value=await firstValueFrom(this.api.confirmAuthenticator(this.enrollmentId,this.code));if(!value.enabled)throw new Error('malformed');if(this.destroyed)return;this.clearTransient();this.state.set('enabled')})}
 async loadDevices(){this.devicesLoading.set(true);try{const value=await firstValueFrom(this.api.authDevices());if(!this.destroyed)this.devices.set(value)}catch{if(!this.destroyed)this.message.set('Registered devices are unavailable right now.')}finally{if(!this.destroyed)this.devicesLoading.set(false)}}
 revokeDevice(deviceId:string){return this.run(async()=>{await firstValueFrom(this.api.revokeDevice(deviceId));await this.loadDevices()})}
 generateRecovery(){return this.run(async()=>{const value=await firstValueFrom(this.api.recoveryCodes());if(!value.shown_once||!value.codes?.length)throw new Error('malformed');if(!this.destroyed)this.recovery.set(value.codes)})}
 private safeError(error:unknown){const response=error as HttpErrorResponse;if(response?.status===401)return 'Your session has expired. Sign in again to continue.';if(response?.status===410)return 'This enrollment has expired. Restart setup to receive a new QR code.';if(response?.status===409)return 'This enrollment is no longer available or was already confirmed. Refresh or restart setup.';if(response?.status===400)return 'That code was not accepted. Enter the current 6-digit code and try again.';if(response?.status===0||response?.status===503)return 'XAI is temporarily unavailable. Check your connection and try again.';return 'The security request could not be completed. Please try again.'}
 private clearTransient(){this.code='';this.enrollmentId='';this.qr.set('');this.uri.set('')}
 ngOnDestroy(){this.destroyed=true;this.clearTransient();this.recovery.set([])}
}

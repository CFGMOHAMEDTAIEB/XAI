import {Component,OnDestroy,signal} from '@angular/core';
import {FormsModule} from '@angular/forms';
import {HttpErrorResponse} from '@angular/common/http';
import {firstValueFrom} from 'rxjs';
import {ApiService} from '../core/api.service';

@Component({standalone:true,imports:[FormsModule],template:`
<div class="heading"><div><h1>Security</h1><p>Protect your account and review authenticator access.</p></div></div>
<article class="panel security-card" aria-labelledby="authenticator-title">
 <div class="security-summary"><div class="security-icon" aria-hidden="true">◇</div><div><p class="eyebrow">Account protection</p><h2 id="authenticator-title">XAI Authenticator</h2><p class="muted">Use time-based codes generated securely by the XAI mobile app.</p></div><span class="status-pill" [class.active]="state()==='enabled'">{{statusLabel()}}</span></div>

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
  @if(showManagement()){<section class="subpanel"><h3>Registered authenticators</h3><p>Your active authenticator factor is enabled. Device-bound approvals, when registered, are managed separately.</p></section>}
  @if(showRecovery()){<section class="subpanel"><h3>Recovery options</h3><p>Recovery codes can be regenerated from the authenticated recovery workflow. Generating new codes replaces prior codes, so it is not performed automatically here.</p></section>}
 }
 @if(message()){<div class="error" role="alert">{{message()}}</div>}
</article>`})
export class SecurityPage implements OnDestroy {
 state=signal('loading');qr=signal('');uri=signal('');message=signal('');busy=signal(false);showManagement=signal(false);showRecovery=signal(false);code='';enrollmentId='';expiresSeconds=600;destroyed=false;
 constructor(private api:ApiService){void this.refresh()}
 statusLabel(){return this.state()==='enabled'?'Active':this.state()==='pending_activation'||this.state().startsWith('awaiting_')?'Pending':'Not configured'}
 expiresMinutes(){return Math.max(1,Math.ceil(this.expiresSeconds/60))}
 validCode(value:string){return /^\d{6}$/.test(value)}
 digitsOnly(){this.code=this.code.replace(/\D/g,'').slice(0,6)}
 async run(action:()=>Promise<void>){if(this.busy())return;this.busy.set(true);this.message.set('');try{await action()}catch(error){if(!this.destroyed)this.message.set(this.safeError(error))}finally{if(!this.destroyed)this.busy.set(false)}}
 refresh(){return this.run(async()=>{const status=await firstValueFrom(this.api.totpStatus());if(!this.destroyed)this.state.set(status.state)})}
 start(){return this.run(async()=>{const value=await firstValueFrom(this.api.startAuthenticator());if(this.destroyed)return;if(!value.enrollment_id||!value.qr_data_uri?.startsWith('data:image/png;base64,')||!value.otpauth_uri?.startsWith('otpauth://'))throw new Error('malformed');this.enrollmentId=value.enrollment_id;this.expiresSeconds=value.expires_in_seconds;this.qr.set(value.qr_data_uri);this.uri.set(value.otpauth_uri);this.state.set('pending_activation')})}
 confirm(){return this.run(async()=>{const value=await firstValueFrom(this.api.confirmAuthenticator(this.enrollmentId,this.code));if(!value.enabled)throw new Error('malformed');if(this.destroyed)return;this.clearTransient();this.state.set('enabled')})}
 private safeError(error:unknown){const response=error as HttpErrorResponse;if(response?.status===401)return 'Your session has expired. Sign in again to continue.';if(response?.status===410)return 'This enrollment has expired. Restart setup to receive a new QR code.';if(response?.status===409)return 'This enrollment is no longer available or was already confirmed. Refresh or restart setup.';if(response?.status===400)return 'That code was not accepted. Enter the current 6-digit code and try again.';if(response?.status===0||response?.status===503)return 'XAI is temporarily unavailable. Check your connection and try again.';return 'The security request could not be completed. Please try again.'}
 private clearTransient(){this.code='';this.enrollmentId='';this.qr.set('');this.uri.set('')}
 ngOnDestroy(){this.destroyed=true;this.clearTransient()}
}

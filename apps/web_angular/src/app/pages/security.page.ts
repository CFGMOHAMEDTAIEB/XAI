import {Component,OnDestroy,signal} from '@angular/core';
import {FormsModule} from '@angular/forms';
import {firstValueFrom} from 'rxjs';
import {ApiService} from '../core/api.service';

@Component({standalone:true,imports:[FormsModule],template:`
<div class="heading"><h1>Account MFA</h1></div>
<article class="panel form-panel">
 <p>Enable TOTP using your authenticator. Email verification comes first; MFA is active only after the server accepts a current authenticator code.</p>
 <p>Current state: {{state()}}</p>
 <button [disabled]="busy()" (click)="refresh()">Refresh status</button>
 @if(state()==='not_configured'||state()==='expired'){
  <button [disabled]="busy()" (click)="enroll(state()==='expired')">Start MFA enrollment</button>
 }
 @if(state()==='awaiting_email'){
  <label>Email verification code<input [(ngModel)]="emailCode" inputmode="numeric" maxlength="6" autocomplete="one-time-code" [disabled]="busy()"></label>
  <button [disabled]="busy()||!validCode(emailCode)" (click)="verifyEmail()">Verify email</button>
  <button [disabled]="busy()" (click)="resend()">Resend email code</button>
  <p>Resend requires a 60-second cooldown; at most five sends per hour. Codes expire in at most ten minutes.</p>
 }
 @if(state()==='awaiting_totp'){
  @if(secret()){
   <p>Add this server-issued secret to your authenticator as a time-based, six-digit code with a 30-second period. Store it before confirming. It is shown only in this page's memory.</p>
   <code style="overflow-wrap:anywhere">{{secret()}}</code>
  } @else {
   <p>Use the authenticator already provisioned for this enrollment. If you lost the secret, restart enrollment; it cannot be retrieved again.</p>
  }
  <label>Authenticator code<input [(ngModel)]="totpCode" inputmode="numeric" maxlength="6" autocomplete="one-time-code" [disabled]="busy()"></label>
  <button [disabled]="busy()||!validCode(totpCode)" (click)="verifyTotp()">Confirm TOTP and enable MFA</button>
 }
 @if(state()==='awaiting_email'||state()==='awaiting_totp'){
  <details><summary>Restart enrollment</summary><p>This invalidates the pending secret. It does not replace active MFA.</p><button [disabled]="busy()" (click)="enroll(true)">Start a new pending enrollment</button></details>
 }
 @if(state()==='enabled'){<p>MFA is enabled. Future sign-ins require your current authenticator code.</p>}
 @if(busy()){<p role="status">Working...</p>}
 @if(message()){<p role="status">{{message()}}</p>}
</article>`})
export class SecurityPage implements OnDestroy{
 state=signal('unknown');secret=signal('');busy=signal(false);message=signal('');
 emailCode='';totpCode='';enrollmentId='';private destroyed=false;
 constructor(private api:ApiService){void this.refresh()}
 validCode(value:string){return /^\d{6}$/.test(value)}
 private async run(action:()=>Promise<void>){
  if(this.busy())return;this.busy.set(true);this.message.set('');
  try{await action()}catch{if(!this.destroyed)this.message.set('MFA request failed. Check the code, expiry or cooldown and retry. If delivery or enrollment state is uncertain, refresh status.')}
  finally{if(!this.destroyed)this.busy.set(false)}
 }
 refresh(){return this.run(async()=>{
  const status=await firstValueFrom(this.api.totpStatus());if(this.destroyed)return;
  if(status.enrollment_id!==this.enrollmentId||status.state!=='awaiting_totp')this.secret.set('');
  this.enrollmentId=status.enrollment_id||'';this.state.set(status.state);
 })}
 enroll(restart=false){return this.run(async()=>{
  const status=await firstValueFrom(this.api.enrollTotp(restart));if(this.destroyed)return;
  this.secret.set('');this.emailCode='';this.totpCode='';this.enrollmentId=status.enrollment_id;this.state.set(status.state);
 })}
 resend(){return this.run(async()=>{const status=await firstValueFrom(this.api.resendTotp());if(this.destroyed)return;this.enrollmentId=status.enrollment_id;this.emailCode='';this.state.set(status.state);this.message.set('Email provider accepted the verification request. Check your inbox.');})}
 verifyEmail(){return this.run(async()=>{
  const result=await firstValueFrom(this.api.confirmEmail(this.enrollmentId,this.emailCode));if(this.destroyed)return;
  this.emailCode='';this.secret.set(result.secret);this.state.set('awaiting_totp');
 })}
 verifyTotp(){return this.run(async()=>{
  const result=await firstValueFrom(this.api.confirmTotp(this.enrollmentId,this.totpCode));if(!result.enabled)throw new Error('Not enabled');if(this.destroyed)return;
  this.secret.set('');this.totpCode='';this.state.set('enabled');
 })}
 ngOnDestroy(){this.destroyed=true;this.secret.set('');this.emailCode='';this.totpCode='';this.enrollmentId=''}
}


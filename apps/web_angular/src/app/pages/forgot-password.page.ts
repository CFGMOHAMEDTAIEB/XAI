import {Component,signal} from '@angular/core';
import {FormsModule} from '@angular/forms';
import {HttpClient} from '@angular/common/http';
import {RouterLink} from '@angular/router';
import {firstValueFrom} from 'rxjs';
import {environment} from '../../environments/environment';

@Component({standalone:true,imports:[FormsModule,RouterLink],template:`
<main class="auth-page"><section class="auth-card"><div class="logo" aria-hidden="true">XC</div><p class="eyebrow">Account recovery</p><h1>Reset password</h1>
 @if(step()===1){<p class="muted">Enter your account email or international phone number.</p><form (ngSubmit)="send()"><label for="reset-id">Email or phone</label><input id="reset-id" name="identifier" [(ngModel)]="identifier" autocomplete="username" required><button class="primary" [disabled]="busy()||!identifier">{{busy()?'Sendingâ€¦':'Send reset code'}}</button></form>}
 @if(step()===2){<p class="muted">If the account is eligible, a 6-digit code has been sent to its email address.</p><form (ngSubmit)="verify()"><label for="reset-code">Code</label><input id="reset-code" class="otp-input" name="code" [(ngModel)]="code" inputmode="numeric" maxlength="6" (input)="digitsOnly()"><button class="primary" [disabled]="busy()||!validCode()">{{busy()?'Verifyingâ€¦':'Verify code'}}</button></form>}
 @if(step()===3){<form (ngSubmit)="reset()"><label for="new-password">New password</label><input id="new-password" type="password" name="password" [(ngModel)]="password" autocomplete="new-password"><label for="confirm-new-password">Confirm password</label><input id="confirm-new-password" type="password" name="confirm" [(ngModel)]="confirm" autocomplete="new-password"><button class="primary" [disabled]="busy()||!validPassword()">{{busy()?'Resettingâ€¦':'Reset password'}}</button></form>}
 @if(step()===4){<div class="success-banner" role="status">Your password has been reset successfully.</div>}
 @if(message()){<div class="error" role="alert">{{message()}}</div>}<p class="auth-switch"><a routerLink="/login">Back to sign in</a></p>
</section></main>`})
export class ForgotPasswordPage{
 step=signal(1);busy=signal(false);message=signal('');identifier='';code='';password='';confirm='';private resetToken='';
 constructor(private http:HttpClient){}validCode(){return /^\d{6}$/.test(this.code)}digitsOnly(){this.code=this.code.replace(/\D/g,'').slice(0,6)}
 validPassword(){const bytes=new TextEncoder().encode(this.password).length;return this.password.length>=10&&bytes<=72&&this.password===this.confirm}
 async send(){await this.run(async()=>{await firstValueFrom(this.http.post(`${environment.apiUrl}/auth/password/forgot`,{identifier:this.identifier}));this.step.set(2)})}
 async verify(){await this.run(async()=>{const value=await firstValueFrom(this.http.post<{reset_token:string}>(`${environment.apiUrl}/auth/password/verify-code`,{identifier:this.identifier,code:this.code}));this.resetToken=value.reset_token;this.step.set(3)})}
 async reset(){if(!this.validPassword()){this.message.set('Use 10 or more characters and make both passwords match.');return}await this.run(async()=>{await firstValueFrom(this.http.post(`${environment.apiUrl}/auth/password/reset`,{reset_token:this.resetToken,new_password:this.password}));this.resetToken='';this.password=this.confirm='';this.step.set(4)})}
 private async run(action:()=>Promise<void>){if(this.busy())return;this.busy.set(true);this.message.set('');try{await action()}catch{this.message.set('The request could not be completed. Check the details or try again later.')}finally{this.busy.set(false)}}
}

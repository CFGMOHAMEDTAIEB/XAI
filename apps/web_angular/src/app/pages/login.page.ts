import {Component,signal} from '@angular/core';
import {FormsModule} from '@angular/forms';
import {HttpErrorResponse} from '@angular/common/http';
import {Router,RouterLink} from '@angular/router';
import {AuthService} from '../core/auth.service';

@Component({standalone:true,imports:[FormsModule,RouterLink],template:`
<main class="auth-page"><section class="auth-card" aria-labelledby="login-title">
 <div class="logo" aria-hidden="true">XD</div>
 @if(step()==='credentials') {
  <p class="eyebrow">XAICD secure workspace</p><h1 id="login-title">Welcome back</h1>
  <p class="muted">Sign in to manage compressed files and secure shares.</p>
  <form (ngSubmit)="submitCredentials()" novalidate>
   <label for="login-email">Email</label><input id="login-email" type="email" name="email" [(ngModel)]="email" autocomplete="username" required [disabled]="busy()">
   <label for="login-password">Password</label><input id="login-password" type="password" name="password" [(ngModel)]="password" autocomplete="current-password" required [disabled]="busy()">
   <button class="primary" [disabled]="busy()||!email||!password">{{busy()?'Signing in…':'Sign in'}}</button>
  </form>
  <p class="auth-switch"><a routerLink="/forgot-password">Forgot password?</a></p>
  <p class="auth-switch">New to XAICD? <a routerLink="/register">Create an account</a></p>
 } @else {
  <p class="eyebrow">Additional verification</p><h1 id="login-title">Verify your identity</h1>
  <p class="muted">Enter the code from your XAICD Authenticator app.</p>
  <form (ngSubmit)="verifyCode()" novalidate>
   <label for="login-totp">6-digit authenticator code</label>
   <input id="login-totp" class="otp-input" name="totp" [(ngModel)]="totp" maxlength="6" inputmode="numeric" pattern="[0-9]{6}" autocomplete="one-time-code" autofocus [disabled]="busy()" (input)="digitsOnly()">
   <button class="primary" [disabled]="busy()||!validCode()">{{busy()?'Verifying…':'Verify'}}</button>
   <button type="button" class="secondary" [disabled]="busy()" (click)="back()">Back to sign in</button>
  </form>
 }
 @if(error()){<div class="error" role="alert">{{error()}}</div>}
 @if(busy()){<span class="sr-only" role="status">Authentication request in progress</span>}
</section></main>`})
export class LoginPage {
 email='';password='';totp='';step=signal<'credentials'|'mfa'>('credentials');busy=signal(false);error=signal('');
 constructor(private auth:AuthService,private router:Router){}
 validCode(){return /^\d{6}$/.test(this.totp)}
 digitsOnly(){this.totp=this.totp.replace(/\D/g,'').slice(0,6)}
 async submitCredentials(){if(this.busy()||!this.email||!this.password)return;await this.attempt(false)}
 async verifyCode(){if(this.busy()||!this.validCode())return;await this.attempt(true)}
 back(){this.auth.cancelMfa();this.step.set('credentials');this.totp='';this.password='';this.error.set('')}
 private async attempt(withCode:boolean){this.busy.set(true);this.error.set('');try{const session=withCode?await this.auth.verifyMfa(this.totp):await this.auth.login(this.email,this.password);if(!withCode)this.password='';await this.router.navigateByUrl(session.mfa_enabled?'/dashboard':'/security')}catch(error){
   const response=error as HttpErrorResponse;const detail=typeof response?.error?.detail==='string'?response.error.detail:'';
   if(!withCode&&response?.status===401&&this.auth.hasMfaChallenge()){this.step.set('mfa');this.totp='';this.password=''}
   else if(withCode&&response?.status===401)this.error.set('Invalid verification code. Please try again.');
   else if(response?.status===403){this.error.set('Your account still needs verification.');void this.router.navigate(['/verify-account'],{state:{email:this.email}})}
   else if(response?.status===0||response?.status===503)this.error.set('XAICD is temporarily unavailable. Check your connection and try again.');
   else this.error.set('Sign-in failed. Check your credentials and try again.');
  }finally{this.busy.set(false)}}
}

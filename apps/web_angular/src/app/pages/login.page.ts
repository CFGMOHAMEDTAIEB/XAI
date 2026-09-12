import {Component,signal} from '@angular/core';
import {FormsModule} from '@angular/forms';
import {HttpErrorResponse} from '@angular/common/http';
import {Router,RouterLink} from '@angular/router';
import {AuthService} from '../core/auth.service';

@Component({standalone:true,imports:[FormsModule,RouterLink],template:`
<main class="auth-page"><section class="auth-card" aria-labelledby="login-title">
 <div class="logo" aria-hidden="true">XC</div>
 @if(step()==='credentials') {
  <p class="eyebrow">XAI secure workspace</p><h1 id="login-title">Welcome back</h1>
  <p class="muted">Sign in to manage compressed files and secure shares.</p>
  <form (ngSubmit)="submitCredentials()" novalidate>
   <label for="login-email">Email</label><input id="login-email" type="email" name="email" [(ngModel)]="email" autocomplete="username" required [disabled]="busy()">
   <label for="login-password">Password</label><input id="login-password" type="password" name="password" [(ngModel)]="password" autocomplete="current-password" required [disabled]="busy()">
   <button class="primary" [disabled]="busy()||!email||!password">{{busy()?'Signing in…':'Sign in'}}</button>
  </form>
  <p class="auth-switch">New to XAI? <a routerLink="/register">Create an account</a></p>
 } @else {
  <p class="eyebrow">Additional verification</p><h1 id="login-title">Verify your identity</h1>
  <p class="muted">Enter the code from your XAI Authenticator app.</p>
  <form (ngSubmit)="verifyCode()" novalidate>
   <label for="login-totp">6-digit authenticator code</label>
   <input id="login-totp" class="otp-input" name="totp" [(ngModel)]="totp" maxlength="6" inputmode="numeric" pattern="[0-9]{6}" autocomplete="one-time-code" autofocus [disabled]="busy()" (input)="digitsOnly()">
   <button class="primary" [disabled]="busy()||!validCode()">{{busy()?'Verifying…':'Verify'}}</button>
   <button type="button" class="secondary" [disabled]="busy()" (click)="back()">Back</button>
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
 back(){this.step.set('credentials');this.totp='';this.error.set('')}
 private async attempt(withCode:boolean){this.busy.set(true);this.error.set('');try{await this.auth.login(this.email,this.password,withCode?this.totp:undefined);await this.router.navigateByUrl('/dashboard')}catch(error){
   const response=error as HttpErrorResponse;const detail=typeof response?.error?.detail==='string'?response.error.detail:'';
   if(!withCode&&response?.status===401&&detail==='Valid TOTP code required'){this.step.set('mfa');this.totp=''}
   else if(withCode&&response?.status===401)this.error.set('That code was not accepted. Enter the current 6-digit code and try again.');
   else if(response?.status===0||response?.status===503)this.error.set('XAI is temporarily unavailable. Check your connection and try again.');
   else this.error.set('Sign-in failed. Check your credentials and try again.');
  }finally{this.busy.set(false)}}
}

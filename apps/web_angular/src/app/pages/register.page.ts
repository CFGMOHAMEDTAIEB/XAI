import {Component,signal} from '@angular/core';
import {FormsModule} from '@angular/forms';
import {HttpErrorResponse} from '@angular/common/http';
import {Router,RouterLink} from '@angular/router';
import {AuthService} from '../core/auth.service';

@Component({standalone:true,imports:[FormsModule,RouterLink],template:`
<main class="auth-page"><section class="auth-card" aria-labelledby="register-title">
 <div class="logo" aria-hidden="true">XD</div><p class="eyebrow">Create your workspace</p><h1 id="register-title">Create account</h1>
 <p class="muted">Create your account, then verify your email. You can add XAICD Authenticator after signing in.</p>
 <form (ngSubmit)="submit()" novalidate>
  <label for="register-name">Full name</label><input id="register-name" name="fullName" [(ngModel)]="fullName" (ngModelChange)="clearFeedback()" autocomplete="name" required [disabled]="busy()">
  <label for="register-email">Email</label><input id="register-email" type="email" name="email" [(ngModel)]="email" (ngModelChange)="clearFeedback()" autocomplete="email" required [disabled]="busy()">
  <label for="register-phone">Phone number</label><input id="register-phone" type="tel" name="phone" [(ngModel)]="phone" (ngModelChange)="clearFeedback()" autocomplete="tel" placeholder="+33 6 12 34 56 78" required [disabled]="busy()">
  <label for="register-password">Password</label><input id="register-password" type="password" name="password" [(ngModel)]="password" (ngModelChange)="clearFeedback()" autocomplete="new-password" required [disabled]="busy()" aria-describedby="password-help">
  <small id="password-help">Use at least 10 characters.</small>
  <label for="register-confirm">Confirm password</label><input id="register-confirm" type="password" name="confirmPassword" [(ngModel)]="confirmPassword" (ngModelChange)="clearFeedback()" autocomplete="new-password" required [disabled]="busy()">
  @if(validation()){<div class="field-error" role="alert">{{validation()}}</div>}
  <button class="primary" [disabled]="busy()">{{busy()?'Creating account…':'Create account'}}</button>
 </form>
 @if(error()){<div class="error" role="alert">{{error()}}</div>}
 @if(verificationPending()){<p class="auth-switch"><a routerLink="/verify-account" [state]="{email:normalizedEmail(),deliveryUnavailable:emailDeliveryUnavailable()}">Go to email verification</a></p>}
 <p class="auth-switch">Already have an account? <a routerLink="/login">Sign in</a></p>
</section></main>`})
export class RegisterPage {
 fullName='';email='';phone='';password='';confirmPassword='';busy=signal(false);error=signal('');validation=signal('');verificationPending=signal(false);emailDeliveryUnavailable=signal(false);
 constructor(private auth:AuthService,private router:Router){}
 normalizedEmail(){return this.email.trim().toLowerCase()}
 clearFeedback(){this.validation.set('');this.error.set('');this.verificationPending.set(false);this.emailDeliveryUnavailable.set(false)}
 validate(){
  if(!this.fullName.trim()||this.fullName.trim().length>120)return 'Enter your full name.';
  if(!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(this.normalizedEmail()))return 'Enter a valid email address.';
  if(!/^\+(?:[\s().-]*\d){8,15}$/.test(this.phone.trim()))return 'Enter an international phone number including country code.';
  const bytes=new TextEncoder().encode(this.password).length;
  if(this.password.length<10)return 'Password must contain at least 10 characters.';
  if(bytes>72)return 'Password must not exceed 72 UTF-8 bytes.';
  if(this.password!==this.confirmPassword)return 'Passwords do not match.';
  return '';
 }
 async submit(){if(this.busy())return;const issue=this.validate();this.validation.set(issue);this.error.set('');this.verificationPending.set(false);this.emailDeliveryUnavailable.set(false);if(issue)return;this.busy.set(true);try{await this.auth.register(this.fullName.trim().replace(/\s+/g,' '),this.normalizedEmail(),this.phone.trim(),this.password);await this.router.navigate(['/verify-account'],{state:{email:this.normalizedEmail()}})}catch(error){
  const status=(error as HttpErrorResponse)?.status;
  if(status===503){this.verificationPending.set(true);this.emailDeliveryUnavailable.set(true);this.error.set('Your account was created, but the verification email could not be sent. Go to email verification and request a new code.')}
  else if(status===409){await this.router.navigate(['/verify-account'],{state:{email:this.normalizedEmail()}})}
  else if(status===422)this.error.set('Check your name, email, phone number, and password, then try again.');
  else if(status===403)this.error.set('This account cannot be created here. Contact your administrator.');
  else if(status===0)this.error.set('Cannot reach XAICD right now. Check your connection and try again.');
  else this.error.set('Account creation could not be completed. Please try again later.');
 }finally{this.busy.set(false)}}
}

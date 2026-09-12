import {Component,signal} from '@angular/core';
import {FormsModule} from '@angular/forms';
import {Router,RouterLink} from '@angular/router';
import {AuthService} from '../core/auth.service';

@Component({standalone:true,imports:[FormsModule,RouterLink],template:`
<main class="auth-page"><section class="auth-card" aria-labelledby="register-title">
 <div class="logo" aria-hidden="true">XC</div><p class="eyebrow">Create your workspace</p><h1 id="register-title">Create account</h1>
 <p class="muted">Start with email and password. You can add XAI Authenticator from Security after signing in.</p>
 <form (ngSubmit)="submit()" novalidate>
  <label for="register-email">Email</label><input id="register-email" type="email" name="email" [(ngModel)]="email" autocomplete="email" required [disabled]="busy()">
  <label for="register-password">Password</label><input id="register-password" type="password" name="password" [(ngModel)]="password" autocomplete="new-password" required [disabled]="busy()" aria-describedby="password-help">
  <small id="password-help">Use at least 10 characters.</small>
  <label for="register-confirm">Confirm password</label><input id="register-confirm" type="password" name="confirmPassword" [(ngModel)]="confirmPassword" autocomplete="new-password" required [disabled]="busy()">
  @if(validation()){<div class="field-error" role="alert">{{validation()}}</div>}
  <button class="primary" [disabled]="busy()">{{busy()?'Creating account…':'Create account'}}</button>
 </form>
 @if(error()){<div class="error" role="alert">{{error()}}</div>}
 <p class="auth-switch">Already have an account? <a routerLink="/login">Sign in</a></p>
</section></main>`})
export class RegisterPage {
 email='';password='';confirmPassword='';busy=signal(false);error=signal('');validation=signal('');
 constructor(private auth:AuthService,private router:Router){}
 validate(){
  if(!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(this.email))return 'Enter a valid email address.';
  const bytes=new TextEncoder().encode(this.password).length;
  if(this.password.length<10)return 'Password must contain at least 10 characters.';
  if(bytes>72)return 'Password must not exceed 72 UTF-8 bytes.';
  if(this.password!==this.confirmPassword)return 'Passwords do not match.';
  return '';
 }
 async submit(){if(this.busy())return;const issue=this.validate();this.validation.set(issue);this.error.set('');if(issue)return;this.busy.set(true);try{await this.auth.register(this.email,this.password);await this.router.navigateByUrl('/dashboard')}catch{this.error.set('Account creation could not be completed. Check your details or try again later.')}finally{this.busy.set(false)}}
}

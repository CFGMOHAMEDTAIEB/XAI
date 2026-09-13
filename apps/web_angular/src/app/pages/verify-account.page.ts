import {Component,OnDestroy,signal} from '@angular/core';
import {FormsModule} from '@angular/forms';
import {HttpClient} from '@angular/common/http';
import {Router,RouterLink} from '@angular/router';
import {firstValueFrom} from 'rxjs';
import {environment} from '../../environments/environment';

@Component({standalone:true,imports:[FormsModule,RouterLink],template:`
<main class="auth-page"><section class="auth-card"><div class="logo" aria-hidden="true">XC</div>
 <p class="eyebrow">Account security</p><h1>Verify your account</h1><p class="muted">We sent a 6-digit code to your email.</p>
 <form (ngSubmit)="verify()"><label for="verify-email">Email</label><input id="verify-email" type="email" name="email" [(ngModel)]="email" autocomplete="email" required [disabled]="busy()">
  <label for="verify-code">6-digit code</label><input id="verify-code" class="otp-input" name="code" [(ngModel)]="code" inputmode="numeric" maxlength="6" autocomplete="one-time-code" (input)="digitsOnly()" [disabled]="busy()">
  <button class="primary" [disabled]="busy()||!validCode()">{{busy()?'Verifying…':'Verify account'}}</button>
  <button type="button" class="secondary" [disabled]="busy()||cooldown()>0" (click)="resend()">{{cooldown()>0?'Resend in '+cooldown()+'s':'Resend code'}}</button>
 </form>@if(message()){<div [class.error]="!success()" [class.success-banner]="success()" role="status">{{message()}}</div>}
 <p class="auth-switch"><a routerLink="/login">Back to sign in</a></p>
</section></main>`})
export class VerifyAccountPage implements OnDestroy{
 email=history.state?.email||'';code='';busy=signal(false);message=signal('');success=signal(false);cooldown=signal(0);timer?:number;
 constructor(private http:HttpClient,private router:Router){}
 validCode(){return /^\d{6}$/.test(this.code)}digitsOnly(){this.code=this.code.replace(/\D/g,'').slice(0,6)}
 private startCooldown(){this.cooldown.set(60);this.timer=window.setInterval(()=>{this.cooldown.update(v=>v-1);if(this.cooldown()<=0&&this.timer)clearInterval(this.timer)},1000)}
 async verify(){if(this.busy()||!this.validCode())return;this.busy.set(true);this.message.set('');try{await firstValueFrom(this.http.post(`${environment.apiUrl}/auth/verification/email/confirm`,{identifier:this.email,code:this.code}));this.success.set(true);this.message.set('Your account is verified. You can now sign in.');setTimeout(()=>void this.router.navigateByUrl('/login'),800)}catch{this.message.set('That code is invalid or expired. Request a new code and try again.')}finally{this.busy.set(false)}}
 async resend(){if(this.busy()||this.cooldown()>0||!this.email)return;this.busy.set(true);try{await firstValueFrom(this.http.post(`${environment.apiUrl}/auth/verification/email/send`,{identifier:this.email}));this.message.set('If available, a new code has been sent.');this.startCooldown()}catch{this.message.set('A new code cannot be sent yet. Please try again later.')}finally{this.busy.set(false)}}
 ngOnDestroy(){if(this.timer)clearInterval(this.timer)}
}

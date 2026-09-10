import {Component,OnDestroy,signal} from '@angular/core';
import {FormsModule} from '@angular/forms';
import {firstValueFrom} from 'rxjs';
import {ApiService} from '../core/api.service';

@Component({standalone:true,imports:[FormsModule],template:`
<div class="heading"><h1>Authenticator</h1></div>
<article class="panel form-panel">
 <h2>Account security</h2><p>Use the XAI mobile app or another standards-compatible authenticator. The setup secret is delivered only in this authenticated, short-lived QR code—never by email.</p>
 <p>Current state: {{state()}}</p>
 <button [hidden]="state()!=='not_configured'&&state()!=='expired'" [disabled]="busy()" (click)="start()">Enable Authenticator</button>
 <section [hidden]="!qr()" aria-labelledby="scan-title"><h3 id="scan-title">Scan with XAI</h3><img [src]="qr()" width="240" height="240" alt="Authenticator enrollment QR code"><p>This QR expires in ten minutes and is replaced if setup restarts.</p>
  <details><summary>Cannot scan?</summary><p>Use the setup URI only as a manual fallback in a trusted authenticator.</p><code style="overflow-wrap:anywhere">{{uri()}}</code></details>
  <label>Code from authenticator<input [(ngModel)]="code" inputmode="numeric" maxlength="6" autocomplete="one-time-code" [disabled]="busy()"></label>
  <button [disabled]="busy()||!validCode(code)" (click)="confirm()">Verify and activate</button>
 </section>
 @if(state()==='enabled') { <p>Authenticator is active. Future sign-ins require a current code.</p> }
 @if(busy()) { <p role="status">Working…</p> } @if(message()) { <p role="alert">{{message()}}</p> }
</article>`})
export class SecurityPage implements OnDestroy {
 state=signal('unknown');qr=signal('');uri=signal('');message=signal('');busy=signal(false);code='';enrollmentId='';destroyed=false;
 constructor(private api:ApiService){void this.refresh()}
 validCode(value:string){return /^\d{6}$/.test(value)}
 async run(action:()=>Promise<void>){if(this.busy())return;this.busy.set(true);this.message.set('');try{await action()}catch{if(!this.destroyed)this.message.set('The request could not be completed. Check the code or expiry and retry.')}finally{if(!this.destroyed)this.busy.set(false)}}
 refresh(){return this.run(async()=>{const status=await firstValueFrom(this.api.totpStatus());if(!this.destroyed)this.state.set(status.state)})}
 start(){return this.run(async()=>{const value=await firstValueFrom(this.api.startAuthenticator());if(this.destroyed)return;this.enrollmentId=value.enrollment_id;this.qr.set(value.qr_data_uri);this.uri.set(value.otpauth_uri);this.state.set('pending_activation')})}
 confirm(){return this.run(async()=>{const value=await firstValueFrom(this.api.confirmAuthenticator(this.enrollmentId,this.code));if(!value.enabled)throw new Error();if(this.destroyed)return;this.code='';this.qr.set('');this.uri.set('');this.state.set('enabled')})}
 ngOnDestroy(){this.destroyed=true;this.code='';this.enrollmentId='';this.qr.set('');this.uri.set('')}
}

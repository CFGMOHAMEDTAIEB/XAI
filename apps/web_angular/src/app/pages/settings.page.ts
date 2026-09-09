import {Component,signal} from '@angular/core';
import {ApiService} from '../core/api.service';
@Component({standalone:true,template:`<div class="heading"><div><h1>Account and settings</h1><p>Your XAI account.</p></div></div><article class="panel form-panel"><p>{{email()}}</p><p>MFA: {{mfa()}}</p><p>Compression uses the backend's verified configuration. Share codes expire after one hour.</p><button [disabled]="busy()" (click)="load()">Refresh account</button><p>{{message()}}</p></article>`})
export class SettingsPage {
 email=signal('');mfa=signal('Unknown');message=signal('');busy=signal(false);
 constructor(private api:ApiService){this.load()}
 load(){if(this.busy())return;this.busy.set(true);this.api.me().subscribe({next:u=>{this.busy.set(false);this.email.set(u.email);this.mfa.set(u.mfa_enabled?'Enabled':'Not enabled');this.message.set('')},error:()=>{this.busy.set(false);this.email.set('');this.mfa.set('Unknown');this.message.set('Account unavailable. Retry when connected.')}})}
}

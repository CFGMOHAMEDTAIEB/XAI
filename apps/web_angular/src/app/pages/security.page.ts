import {Component,signal} from '@angular/core';
import {FormsModule} from '@angular/forms';
import {ApiService} from '../core/api.service';
@Component({standalone:true,imports:[FormsModule],template:`
<div class="heading"><div><h1>Security center</h1><p>Enroll your XAI mobile authenticator.</p></div></div>
<article class="panel form-panel"><button class="primary" (click)="enroll()">Set up TOTP</button>
@if(enrollment();as item){<p>Scan this QR in XAI Authenticator, or use Add account, then Enter secret. Keep the enrollment secret private.</p><img [src]="'data:image/png;base64,'+item.qr_png_base64" alt="Private TOTP enrollment QR"><p>Manual secret: <code>{{item.secret}}</code></p><label>Code from mobile<input [(ngModel)]="code" maxlength="6" inputmode="numeric"></label><button class="primary" [disabled]="code.length!==6" (click)="confirm()">Confirm enrollment</button>}
@if(message()){<p>{{message()}}</p>}</article>`})
export class SecurityPage{
  enrollment=signal<{secret:string;qr_png_base64:string}|null>(null);message=signal('');code='';
  constructor(private api:ApiService){}
  enroll(){this.api.enroll().subscribe({next:r=>{this.enrollment.set(r);this.message.set('')},error:e=>this.message.set(e?.error?.detail??'Enrollment failed')})}
  confirm(){this.api.confirm(this.code).subscribe({next:()=>{this.enrollment.set(null);this.code='';this.message.set('TOTP enabled. Use a mobile code at your next sign-in.')},error:e=>this.message.set(e?.error?.detail??'Confirmation failed')})}
}

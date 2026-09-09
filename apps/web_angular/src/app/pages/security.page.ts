import {Component, signal} from '@angular/core';
import {finalize, timeout} from 'rxjs';
import {ApiService} from '../core/api.service';

@Component({standalone: true, template: `
<div class="heading"><div><h1>Security center</h1><p>Set up MFA in XAI Authenticator.</p></div></div>
<article class="panel form-panel">
  <p>Open the XAI Authenticator mobile app, unlock it, and sign in to the same XAI account.</p>
  <p>Choose Setup Authenticator, verify the code sent to your registered email, then confirm the generated TOTP. The app securely provisions the server-generated secret. Never invent a secret.</p>
  <p>MFA becomes active only after that final confirmation. Until then, sign in with email and password. Once enabled, sign in with your current authenticator code as well.</p>
  <button class="primary" [disabled]="busy()" (click)="refresh()">{{busy() ? 'Checking...' : 'Refresh MFA status'}}</button>
  @if(message()){<p>{{message()}}</p>}
</article>`})
export class SecurityPage {
  busy = signal(false);
  message = signal('');
  constructor(private api: ApiService) {}
  refresh() {
    if (this.busy()) return;
    this.busy.set(true);
    this.api.me().pipe(timeout(15000), finalize(() => this.busy.set(false))).subscribe({
      next: user => this.message.set(user.mfa_enabled ? 'MFA is enabled.' : 'MFA is not enabled. Complete setup in the mobile app.'),
      error: () => this.message.set('Could not check MFA status. Retry or sign in again.')
    });
  }
}

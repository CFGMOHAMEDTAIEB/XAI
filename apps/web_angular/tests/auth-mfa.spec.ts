import {beforeEach,describe,expect,it,vi} from 'vitest';
import {of,throwError} from 'rxjs';
import {SecurityPage} from '../src/app/pages/security.page';
import {AuthService} from '../src/app/core/auth.service';
import {ApiService} from '../src/app/core/api.service';

beforeEach(()=>localStorage.clear());
describe('MFA enrollment state',()=>{
 const setup=async()=>{
  const api={totpStatus:vi.fn(()=>of({state:'not_configured',enrollment_id:null})),enrollTotp:vi.fn(()=>of({state:'awaiting_email',enrollment_id:'fixture-id'})),confirmEmail:vi.fn(()=>of({secret:crypto.randomUUID()})),confirmTotp:vi.fn(()=>of({enabled:true}))};
  const page=new SecurityPage(api as unknown as ApiService);await Promise.resolve();return {api,page};
 };
 it('requires email disclosure and server TOTP confirmation; never persists secret',async()=>{
  const {page}=await setup();await page.enroll();expect(page.state()).toBe('awaiting_email');expect(page.secret()).toBe('');
  page.emailCode=String(crypto.getRandomValues(new Uint32Array(1))[0]%1000000).padStart(6,'0');await page.verifyEmail();
  expect(page.state()).toBe('awaiting_totp');expect(page.secret()).not.toBe('');expect(localStorage.length).toBe(0);
  await page.verifyTotp();expect(page.state()).toBe('enabled');expect(page.secret()).toBe('');
 });
 it('failed confirmation never marks MFA active',async()=>{
  const {api,page}=await setup();await page.enroll();api.confirmTotp.mockReturnValue(throwError(()=>new Error('unavailable')));
  await page.verifyTotp();expect(page.state()).not.toBe('enabled');expect(page.busy()).toBe(false);expect(page.message()).toContain('failed');
 });
 it('navigation clears transient enrollment material',async()=>{
  const {page}=await setup();page.secret.set(crypto.randomUUID());page.ngOnDestroy();expect(page.secret()).toBe('');
 });
});
describe('real authentication transport',()=>{
 it('login always calls backend, including former demo identity',async()=>{
  const http={post:vi.fn(()=>of({access_token:crypto.randomUUID(),refresh_token:crypto.randomUUID()}))};
  const auth=new AuthService(http as never,{navigateByUrl:vi.fn()} as never);
  await auth.login('demo@xai.local',crypto.randomUUID());expect(http.post).toHaveBeenCalledOnce();expect(auth.authenticated()).toBe(true);
  auth.logout();expect(auth.token()).toBe(null);expect(localStorage.length).toBe(0);
 });
 it('MFA code is in an authenticated POST body, never a URL',()=>{
  const http={post:vi.fn(()=>of({}))};const api=new ApiService(http as never);const code=crypto.randomUUID();api.confirmEmail('enrollment',code);
  const [url,body]=http.post.mock.calls[0] as unknown as [string,{code:string}];expect(url).not.toContain(code);expect(body.code).toBe(code);
 });
});

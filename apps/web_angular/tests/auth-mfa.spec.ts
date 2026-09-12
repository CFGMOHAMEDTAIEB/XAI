import {beforeEach,describe,expect,it,vi} from 'vitest';
import {of,throwError} from 'rxjs';
import {LoginPage} from '../src/app/pages/login.page';
import {RegisterPage} from '../src/app/pages/register.page';
import {SecurityPage} from '../src/app/pages/security.page';
import {AuthService} from '../src/app/core/auth.service';
import {ApiService} from '../src/app/core/api.service';

const flush=()=>new Promise(resolve=>setTimeout(resolve,0));
beforeEach(()=>localStorage.clear());

describe('staged login',()=>{
 const setup=(login=vi.fn().mockResolvedValue(undefined))=>{const router={navigateByUrl:vi.fn().mockResolvedValue(true)};return {login,router,page:new LoginPage({login} as never,router as never)}};
 it('normal login completes without showing an MFA challenge',async()=>{const {page,login,router}=setup();page.email='person@example.com';page.password='correct-password';await page.submitCredentials();expect(login).toHaveBeenCalledWith(page.email,page.password,undefined);expect(page.step()).toBe('credentials');expect(router.navigateByUrl).toHaveBeenCalledWith('/dashboard')});
 it('moves to code verification only when valid credentials require MFA',async()=>{const error={status:401,error:{detail:'Valid TOTP code required'}};const {page}=setup(vi.fn().mockRejectedValue(error));page.email='person@example.com';page.password='correct-password';await page.submitCredentials();expect(page.step()).toBe('mfa');expect(page.error()).toBe('')});
 it('handles an invalid TOTP without exposing backend details',async()=>{const login=vi.fn().mockRejectedValueOnce({status:401,error:{detail:'Valid TOTP code required'}}).mockRejectedValueOnce({status:401,error:{detail:'internal detail'}});const {page}=setup(login);page.email='person@example.com';page.password='correct-password';await page.submitCredentials();page.totp='123456';await page.verifyCode();expect(page.step()).toBe('mfa');expect(page.error()).toContain('not accepted');expect(page.error()).not.toContain('internal')});
});

describe('registration',()=>{
 const setup=()=>{const auth={register:vi.fn().mockResolvedValue(undefined)};const router={navigateByUrl:vi.fn().mockResolvedValue(true)};return {auth,router,page:new RegisterPage(auth as never,router as never)}};
 it('validates email, backend password bounds, and matching confirmation',async()=>{const {page,auth}=setup();page.email='bad';page.password='short';page.confirmPassword='different';await page.submit();expect(page.validation()).toContain('valid email');expect(auth.register).not.toHaveBeenCalled();page.email='person@example.com';await page.submit();expect(page.validation()).toContain('10 characters');page.password='correct-password';page.confirmPassword='other-password';await page.submit();expect(page.validation()).toContain('do not match')});
 it('registers without enabling MFA and continues to the dashboard',async()=>{const {page,auth,router}=setup();page.email='person@example.com';page.password=page.confirmPassword='correct-password';await page.submit();expect(auth.register).toHaveBeenCalledWith(page.email,page.password);expect(router.navigateByUrl).toHaveBeenCalledWith('/dashboard')});
});

describe('current authenticator enrollment',()=>{
 const qr='data:image/png;base64,ZmFrZS1wbmc=';const uri='otpauth://totp/XAI:person?secret=TESTONLY&issuer=XAI';
 const setup=async(overrides:Record<string,unknown>={})=>{const api={totpStatus:vi.fn(()=>of({state:'not_configured',enrollment_id:null})),startAuthenticator:vi.fn(()=>of({enrollment_id:'a'.repeat(32),qr_data_uri:qr,otpauth_uri:uri,expires_in_seconds:600})),confirmAuthenticator:vi.fn(()=>of({enabled:true})),...overrides};const page=new SecurityPage(api as unknown as ApiService);await flush();return {api,page}};
 it('shows the backend authenticator status',async()=>{const {page}=await setup();expect(page.state()).toBe('not_configured');expect(page.statusLabel()).toBe('Not configured')});
 it('starts enrollment and retains the authorized QR only in memory',async()=>{const {page,api}=await setup();await page.start();expect(api.startAuthenticator).toHaveBeenCalledOnce();expect(page.state()).toBe('pending_activation');expect(page.qr()).toBe(qr);expect(page.uri()).toBe(uri);expect(localStorage.length).toBe(0)});
 it('verifies the mobile TOTP before activating MFA',async()=>{const {page,api}=await setup();await page.start();page.code='123456';await page.confirm();expect(api.confirmAuthenticator).toHaveBeenCalledWith('a'.repeat(32),'123456');expect(page.state()).toBe('enabled');expect(page.statusLabel()).toBe('Active');expect(page.qr()).toBe('');expect(page.uri()).toBe('')});
 it('does not activate when enrollment confirmation fails',async()=>{const {page}=await setup({confirmAuthenticator:vi.fn(()=>throwError(()=>({status:400,error:{detail:'secret internal message'}})))});await page.start();page.code='123456';await page.confirm();expect(page.state()).toBe('pending_activation');expect(page.message()).toContain('not accepted');expect(page.message()).not.toContain('internal')});
 it('clears all transient provisioning material on navigation',async()=>{const {page}=await setup();await page.start();page.code='123456';page.ngOnDestroy();expect(page.qr()).toBe('');expect(page.uri()).toBe('');expect(page.code).toBe('');expect(page.enrollmentId).toBe('')});
});

describe('real authentication transport',()=>{
 it('supports logout and relogin with the current mobile code',async()=>{let calls=0;const http={post:vi.fn((url:string,body:Record<string,string|null>)=>{if(url.endsWith('/auth/logout'))return of({logged_out:true});calls++;if(calls===1)return throwError(()=>({status:401,error:{detail:'Valid TOTP code required'}}));expect(body.totp_code).toBe('654321');return of({access_token:'access-fixture',refresh_token:'refresh-fixture'})})};const router={navigateByUrl:vi.fn()};const auth=new AuthService(http as never,router as never);await expect(auth.login('person@example.com','correct-password')).rejects.toBeTruthy();await auth.login('person@example.com','correct-password','654321');expect(auth.authenticated()).toBe(true);auth.logout();expect(auth.authenticated()).toBe(false);expect(localStorage.length).toBe(0)});
 it('places MFA codes in POST bodies and never URLs',()=>{const http={post:vi.fn(()=>of({}))};const api=new ApiService(http as never);api.confirmAuthenticator('a'.repeat(32),'123456');const [url,body]=http.post.mock.calls[0] as unknown as [string,{code:string}];expect(url).not.toContain('123456');expect(body.code).toBe('123456')});
});

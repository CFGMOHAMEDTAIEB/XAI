import {beforeEach,describe,expect,it,vi} from 'vitest';
import {of,throwError} from 'rxjs';
import {LoginPage} from '../src/app/pages/login.page';
import {RegisterPage} from '../src/app/pages/register.page';
import {SecurityPage} from '../src/app/pages/security.page';
import {AuthService} from '../src/app/core/auth.service';
import {ApiService} from '../src/app/core/api.service';
import {routes} from '../src/app/app.routes';
import {ShellComponent} from '../src/app/layout/shell.component';
import {DashboardPage} from '../src/app/pages/dashboard.page';
import {SharesPage} from '../src/app/pages/shares.page';

const flush=()=>new Promise(resolve=>setTimeout(resolve,0));
beforeEach(()=>{localStorage.clear();sessionStorage.clear()});

describe('staged login',()=>{
 const setup=(login=vi.fn().mockResolvedValue(undefined))=>{const router={navigateByUrl:vi.fn().mockResolvedValue(true)};return {login,router,page:new LoginPage({login} as never,router as never)}};
 it('normal login completes without showing an MFA challenge',async()=>{const {page,login,router}=setup();page.email='person@example.com';page.password='correct-password';await page.submitCredentials();expect(login).toHaveBeenCalledWith(page.email,page.password,undefined);expect(page.step()).toBe('credentials');expect(router.navigateByUrl).toHaveBeenCalledWith('/dashboard')});
 it('moves to code verification only when valid credentials require MFA',async()=>{const error={status:401,error:{detail:'Valid TOTP code required'}};const {page}=setup(vi.fn().mockRejectedValue(error));page.email='person@example.com';page.password='correct-password';await page.submitCredentials();expect(page.step()).toBe('mfa');expect(page.error()).toBe('')});
 it('handles an invalid TOTP without exposing backend details',async()=>{const login=vi.fn().mockRejectedValueOnce({status:401,error:{detail:'Valid TOTP code required'}}).mockRejectedValueOnce({status:401,error:{detail:'internal detail'}});const {page}=setup(login);page.email='person@example.com';page.password='correct-password';await page.submitCredentials();page.totp='123456';await page.verifyCode();expect(page.step()).toBe('mfa');expect(page.error()).toContain('not accepted');expect(page.error()).not.toContain('internal')});
});

describe('registration',()=>{
 const setup=()=>{const auth={register:vi.fn().mockResolvedValue({verification_required:true})};const router={navigate:vi.fn().mockResolvedValue(true),navigateByUrl:vi.fn().mockResolvedValue(true)};return {auth,router,page:new RegisterPage(auth as never,router as never)}};
 it('validates profile fields, backend password bounds, and matching confirmation',async()=>{const {page,auth}=setup();page.fullName='Test Person';page.phone='+33612345678';page.email='bad';page.password='short';page.confirmPassword='different';await page.submit();expect(page.validation()).toContain('valid email');expect(auth.register).not.toHaveBeenCalled();page.email='person@example.com';await page.submit();expect(page.validation()).toContain('10 characters');page.password='correct-password';page.confirmPassword='other-password';await page.submit();expect(page.validation()).toContain('do not match')});
 it('registers a pending account and continues to verification',async()=>{const {page,auth,router}=setup();page.fullName='Test Person';page.phone='+33612345678';page.email='person@example.com';page.password=page.confirmPassword='correct-password';await page.submit();expect(auth.register).toHaveBeenCalledWith(page.fullName,page.email,page.phone,page.password);expect(router.navigate).toHaveBeenCalledWith(['/verify-account'],{state:{email:page.email}})});
});

describe('current authenticator enrollment',()=>{
 const qr='data:image/png;base64,ZmFrZS1wbmc=';const uri='otpauth://totp/XAI:person?secret=TESTONLY&issuer=XAI';
 const setup=async(overrides:Record<string,unknown>={})=>{const api={me:vi.fn(()=>of({email:'person@example.com',phone_number:'+33612345678',email_verified:true,phone_verified:false})),totpStatus:vi.fn(()=>of({state:'not_configured',enrollment_id:null})),startAuthenticator:vi.fn(()=>of({enrollment_id:'a'.repeat(32),qr_data_uri:qr,otpauth_uri:uri,expires_in_seconds:600})),confirmAuthenticator:vi.fn(()=>of({enabled:true})),authDevices:vi.fn(()=>of([])),revokeDevice:vi.fn(()=>of({status:'revoked'})),recoveryCodes:vi.fn(()=>of({codes:['recovery-one'],shown_once:true})),...overrides};const page=new SecurityPage(api as unknown as ApiService);await flush();return {api,page}};
 it('shows the backend authenticator status',async()=>{const {page}=await setup();expect(page.state()).toBe('not_configured');expect(page.statusLabel()).toBe('Not configured')});
 it('starts enrollment and retains the authorized QR only in memory',async()=>{const {page,api}=await setup();await page.start();expect(api.startAuthenticator).toHaveBeenCalledOnce();expect(page.state()).toBe('pending_activation');expect(page.qr()).toBe(qr);expect(page.uri()).toBe(uri);expect(localStorage.length).toBe(0)});
 it('verifies the mobile TOTP before activating MFA',async()=>{const {page,api}=await setup();await page.start();page.code='123456';await page.confirm();expect(api.confirmAuthenticator).toHaveBeenCalledWith('a'.repeat(32),'123456');expect(page.state()).toBe('enabled');expect(page.statusLabel()).toBe('Active');expect(page.qr()).toBe('');expect(page.uri()).toBe('')});
 it('does not activate when enrollment confirmation fails',async()=>{const {page}=await setup({confirmAuthenticator:vi.fn(()=>throwError(()=>({status:400,error:{detail:'secret internal message'}})))});await page.start();page.code='123456';await page.confirm();expect(page.state()).toBe('pending_activation');expect(page.message()).toContain('not accepted');expect(page.message()).not.toContain('internal')});
 it('clears all transient provisioning material on navigation',async()=>{const {page}=await setup();await page.start();page.code='123456';page.ngOnDestroy();expect(page.qr()).toBe('');expect(page.uri()).toBe('');expect(page.code).toBe('');expect(page.enrollmentId).toBe('')});
 it('lists and revokes only through the authenticated device API',async()=>{const device={device_id:'device_abcdefghijklmnop',platform:'android',app_version:'1.0',status:'active',registered_at:'2026-01-01',last_activity:'2026-01-02'};const {page,api}=await setup({authDevices:vi.fn(()=>of([device]))});await page.loadDevices();expect(page.devices()).toEqual([device]);await page.revokeDevice(device.device_id);expect(api.revokeDevice).toHaveBeenCalledWith(device.device_id)});
});

describe('secure sharing workspace',()=>{
 it('loads owned files, share history and provider capability',async()=>{const api={files:vi.fn(()=>of([{id:1,name:'owned.bin',status:'completed'}])),shares:vi.fn(()=>of([{id:2,file_name:'owned.bin',recipient_email:'recipient@example.com',expires_at:'2026-01-01',status:'active',download_count:0,max_downloads:1}])),emailCapabilities:vi.fn(()=>of({configured:true,artifact_email_supported:false}))};const page=new SharesPage(api as never);await flush();expect(page.files().length).toBe(1);expect(page.shares().length).toBe(1);expect(page.emailSupported()).toBe(false)});
 it('creates and revokes using backend APIs without faking email receipt',async()=>{const api={files:vi.fn(()=>of([])),shares:vi.fn(()=>of([])),emailCapabilities:vi.fn(()=>of({configured:true,artifact_email_supported:true})),share:vi.fn(()=>of({share_code:'SAFE-CODE',expires_at:'2026-01-01',recipient_email:'recipient@example.com'})),revokeShare:vi.fn(()=>of({status:'revoked'}))};const page=new SharesPage(api as never);await flush();page.fileId=7;page.email='recipient@example.com';page.create();await flush();expect(api.share).toHaveBeenCalledWith(7,'recipient@example.com');expect(page.code()).toBe('SAFE-CODE');page.revoke({id:9} as never);await flush();expect(api.revokeShare).toHaveBeenCalledWith(9)});
});

describe('real authentication transport',()=>{
 it('supports logout and relogin with the current mobile code',async()=>{let calls=0;const http={post:vi.fn((url:string,body:Record<string,string|null>)=>{if(url.endsWith('/auth/logout'))return of({logged_out:true});calls++;if(calls===1)return throwError(()=>({status:401,error:{detail:'Valid TOTP code required'}}));expect(body.totp_code).toBe('654321');return of({access_token:'access-fixture',refresh_token:'refresh-fixture'})})};const router={navigateByUrl:vi.fn()};const auth=new AuthService(http as never,router as never);await expect(auth.login('person@example.com','correct-password')).rejects.toBeTruthy();await auth.login('person@example.com','correct-password','654321');expect(auth.authenticated()).toBe(true);auth.logout();expect(auth.authenticated()).toBe(false);expect(localStorage.length).toBe(0)});
 it('places MFA codes in POST bodies and never URLs',()=>{const http={post:vi.fn(()=>of({}))};const api=new ApiService(http as never);api.confirmAuthenticator('a'.repeat(32),'123456');const [url,body]=http.post.mock.calls[0] as unknown as [string,{code:string}];expect(url).not.toContain('123456');expect(body.code).toBe('123456')});
});

describe('authenticated workspace navigation',()=>{
 it('exposes dashboard, compression, restoration, history, security and account routes',()=>{const shell=routes.find(x=>x.path==='');const paths=shell?.children?.map(x=>x.path);expect(paths).toEqual(expect.arrayContaining(['dashboard','compress','inbox','files','security','settings']))});
 it('uses a responsive drawer and real account identity in the shell',()=>{const auth={logout:vi.fn()};const api={me:vi.fn(()=>of({email:'person@example.com',display_name:'Test Person',is_admin:false}))};const shell=new ShellComponent(auth as never,api as never);expect(shell.initials()).toBe('TP');shell.drawer.set(true);shell.close();expect(shell.drawer()).toBe(false)});
 it('derives dashboard totals from real file records',async()=>{const files=[{id:1,name:'one.bin',status:'completed',codec:'static',created_at:'2026-01-01',original_size:10,compressed_size:8},{id:2,name:'two.bin',status:'failed',codec:'static',created_at:'2026-01-02',original_size:10,compressed_size:0}];const api={me:vi.fn(()=>of({display_name:'Test Person'})),files:vi.fn(()=>of(files))};const page=new DashboardPage(api as never);await flush();expect(page.completed()).toBe(1);expect(page.failed()).toBe(1);expect(page.firstName()).toBe('Test')});
});

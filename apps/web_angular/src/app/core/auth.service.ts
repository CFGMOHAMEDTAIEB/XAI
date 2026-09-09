import {Injectable,computed,signal} from '@angular/core';
import {HttpClient} from '@angular/common/http';
import {Router} from '@angular/router';
import {firstValueFrom} from 'rxjs';
import {environment} from '../../environments/environment';
import {AuthToken} from '../models/models';
@Injectable({providedIn:'root'})
export class AuthService {
  private readonly key='xai_access_token';
  private readonly refreshKey='xai_refresh_token';
  private readonly value=signal<string|null>(localStorage.getItem(this.key));
  private refreshing:Promise<string>|null=null;
  private generation=0;
  readonly token=this.value.asReadonly();
  readonly authenticated=computed(()=>this.value()!==null);
  constructor(private http:HttpClient,private router:Router){
    window.addEventListener('storage',event=>{
      if(event.key===this.key||event.key===null){
        this.generation++;
        this.value.set(localStorage.getItem(this.key));
        if(!this.value())void this.router.navigateByUrl('/login');
      }
    });
  }
  async register(email:string,password:string){
    const r=await firstValueFrom(this.http.post<AuthToken>(`${environment.apiUrl}/auth/register`,{email,password}));
    this.save(r.access_token,r.refresh_token);
  }
  async login(email:string,password:string,totp?:string){
    if(environment.demoMode&&email==='demo@xai.local'){this.save('demo-token');return;}
    const r=await firstValueFrom(this.http.post<AuthToken>(`${environment.apiUrl}/auth/login`,{email,password,totp_code:totp||null}));
    this.save(r.access_token,r.refresh_token);
  }
  refresh():Promise<string>{
    if(this.refreshing)return this.refreshing;
    const generation=this.generation;
    this.refreshing=(async()=>{
      try{
        const refresh_token=localStorage.getItem(this.refreshKey);
        if(!refresh_token)throw new Error('Sign in again.');
        const r=await firstValueFrom(this.http.post<AuthToken>(`${environment.apiUrl}/auth/refresh`,{refresh_token}));
        if(generation!==this.generation)throw new Error('Session changed. Sign in again.');
        this.save(r.access_token,r.refresh_token);
        return r.access_token;
      }catch(error){if(generation===this.generation)this.clearSession();throw error;}
      finally{this.refreshing=null;}
    })();
    return this.refreshing;
  }
  logout(){
    const refresh_token=localStorage.getItem(this.refreshKey);
    this.clearSession();
    if(refresh_token)this.http.post(`${environment.apiUrl}/auth/logout`,{refresh_token}).subscribe({error:()=>{}});
  }
  clearSession(){
    this.generation++;
    localStorage.removeItem(this.key);localStorage.removeItem(this.refreshKey);
    this.value.set(null);void this.router.navigateByUrl('/login');
  }
  private save(token:string,refresh?:string){
    localStorage.setItem(this.key,token);
    if(refresh)localStorage.setItem(this.refreshKey,refresh);else localStorage.removeItem(this.refreshKey);
    this.value.set(token);
  }
}

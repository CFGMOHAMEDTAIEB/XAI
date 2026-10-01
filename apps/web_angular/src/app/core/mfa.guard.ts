import {inject} from '@angular/core';
import {CanActivateFn,Router} from '@angular/router';
import {catchError,map,of} from 'rxjs';
import {ApiService} from './api.service';

export const mfaGuard:CanActivateFn=()=>{
  const api=inject(ApiService);
  const router=inject(Router);
  return api.me().pipe(
    map(profile=>profile.mfa_enabled||router.createUrlTree(['/security'])),
    catchError(()=>of(router.createUrlTree(['/login'])))
  );
};

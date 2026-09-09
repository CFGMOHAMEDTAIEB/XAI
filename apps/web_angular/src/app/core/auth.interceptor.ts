import {HttpInterceptorFn,HttpErrorResponse} from '@angular/common/http';
import {inject} from '@angular/core';
import {catchError,from,switchMap,throwError,timeout} from 'rxjs';
import {AuthService} from './auth.service';
import {environment} from '../../environments/environment';
export const authInterceptor:HttpInterceptorFn=(req,next)=>{
  if(!req.url.startsWith(`${environment.apiUrl}/`))return next(req);
  const auth=inject(AuthService);
  const anonymous=/\/auth\/(login|register|refresh|logout)$/.test(req.url);
  const token=auth.token();
  const request=token&&!anonymous?req.clone({setHeaders:{Authorization:`Bearer ${token}`}}):req;
  const limit=/\/compression\/|\/download$/.test(req.url)?600000:40000;
  return next(request).pipe(timeout(limit),catchError((error:HttpErrorResponse)=>{
    if(error.status!==401||anonymous||!token)return throwError(()=>error);
    return from(auth.refresh()).pipe(
      switchMap(fresh=>next(req.clone({setHeaders:{Authorization:`Bearer ${fresh}`}})).pipe(timeout(limit))),
      catchError(failure=>{if(failure.status===401)auth.clearSession();return throwError(()=>failure);})
    );
  }));
};

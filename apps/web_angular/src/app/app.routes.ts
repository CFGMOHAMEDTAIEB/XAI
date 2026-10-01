import {Routes} from '@angular/router';
import {authGuard} from './core/auth.guard';
import {mfaGuard} from './core/mfa.guard';
export const routes:Routes=[
 {path:'register',loadComponent:()=>import('./pages/register.page').then(m=>m.RegisterPage)},
 {path:'login',loadComponent:()=>import('./pages/login.page').then(m=>m.LoginPage)},
 {path:'verify-account',loadComponent:()=>import('./pages/verify-account.page').then(m=>m.VerifyAccountPage)},
 {path:'forgot-password',loadComponent:()=>import('./pages/forgot-password.page').then(m=>m.ForgotPasswordPage)},
 {path:'',canActivate:[authGuard],loadComponent:()=>import('./layout/shell.component').then(m=>m.ShellComponent),children:[
  {path:'',pathMatch:'full',redirectTo:'dashboard'},
  {path:'dashboard',canActivate:[mfaGuard],loadComponent:()=>import('./pages/dashboard.page').then(m=>m.DashboardPage)},
  {path:'files',canActivate:[mfaGuard],loadComponent:()=>import('./pages/files.page').then(m=>m.FilesPage)},
  {path:'compress',canActivate:[mfaGuard],loadComponent:()=>import('./pages/compress.page').then(m=>m.CompressPage)},
  {path:'shares',canActivate:[mfaGuard],loadComponent:()=>import('./pages/shares.page').then(m=>m.SharesPage)},
  {path:'inbox',canActivate:[mfaGuard],loadComponent:()=>import('./pages/inbox.page').then(m=>m.InboxPage)},
  {path:'security',loadComponent:()=>import('./pages/security.page').then(m=>m.SecurityPage)},
  {path:'settings',canActivate:[mfaGuard],loadComponent:()=>import('./pages/settings.page').then(m=>m.SettingsPage)}]},
 {path:'**',redirectTo:''}
];

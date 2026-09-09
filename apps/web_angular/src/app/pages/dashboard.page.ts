import {Component,signal} from '@angular/core';
import {RouterLink} from '@angular/router';
import {ApiService} from '../core/api.service';
import {FileItem} from '../models/models';
@Component({standalone:true,imports:[RouterLink],template:`<div class="heading"><div><h1>Dashboard</h1><p>Your cloud compression activity.</p></div><a class="primary" routerLink="/compress">New compression</a></div><article class="panel"><h2>Recent activity</h2><button [disabled]="loading()" (click)="load()">Refresh</button>@if(loading()){<p>Loading...</p>}@if(error()){<p>{{error()}}</p>}@for(f of files();track f.id){<div class="activity"><b>{{f.name}}</b><span>{{f.status}}</span></div>}@if(!loading()&&!files().length&&!error()){<p>No cloud operations yet.</p>}</article><article class="panel"><h2>Quick actions</h2><div class="quick"><a routerLink="/files">History and downloads</a><a routerLink="/compress">Compress a file</a><a routerLink="/shares">Create a secure share</a><a routerLink="/inbox">Decompress or redeem a code</a><a routerLink="/security">Review MFA</a></div></article>`})
export class DashboardPage {
 files=signal<FileItem[]>([]);loading=signal(false);error=signal('');
 constructor(private api:ApiService){this.load()}
 load(){if(this.loading())return;this.loading.set(true);this.error.set('');this.api.files().subscribe({next:files=>{this.files.set(files.slice(0,5));this.loading.set(false)},error:()=>{this.loading.set(false);this.error.set('Activity unavailable. Retry when connected.')}})}
}

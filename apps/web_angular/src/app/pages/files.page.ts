import {Component,OnInit,signal} from '@angular/core';
import {DatePipe,DecimalPipe} from '@angular/common';
import {ApiService} from '../core/api.service';
import {saveBlob} from '../core/download';
import {FileItem} from '../models/models';
@Component({standalone:true,imports:[DatePipe,DecimalPipe],template:`
<div class="heading"><div><h1>History</h1><p>Your cloud compression artifacts.</p></div><button [disabled]="loading()" (click)="load()">Refresh</button></div>
@if(loading()){<p>Loading history...</p>}@if(message()){<p role="status">{{message()}}</p>}
<article class="panel table-wrap"><table><thead><tr><th>Name</th><th>Codec</th><th>Original</th><th>Output</th><th>Saving</th><th>Status</th><th>Date</th><th>Download</th></tr></thead><tbody>
@for(f of files();track f.id){<tr><td><b>{{f.name}}</b></td><td>{{f.codec}}</td><td>{{f.original_size/1024|number:'1.0-1'}} KiB</td><td>{{f.compressed_size/1024|number:'1.0-1'}} KiB</td><td>{{saving(f)|number:'1.1-1'}}%</td><td>{{f.status}}</td><td>{{f.created_at|date:'medium'}}</td><td><button [disabled]="downloading()!==null" (click)="download(f)">Download</button></td></tr>}
</tbody></table>@if(!loading()&&!files().length&&!message()){<p>No cloud files to display.</p>}</article>`})
export class FilesPage implements OnInit {
  files=signal<FileItem[]>([]);loading=signal(false);message=signal('');downloading=signal<number|null>(null);
  constructor(private api:ApiService){}
  ngOnInit(){this.load()}
  load(){if(this.loading())return;this.loading.set(true);this.message.set('');this.api.files().subscribe({next:v=>{this.files.set(v);this.loading.set(false)},error:()=>{this.loading.set(false);this.message.set('History unavailable. Check your connection and retry.')}})}
  saving(f:FileItem){return f.original_size?100*(1-f.compressed_size/f.original_size):0}
  download(f:FileItem){if(this.downloading()!==null)return;this.downloading.set(f.id);this.api.download(f.id).subscribe({next:b=>{saveBlob(b,f.name+'.xaic');this.downloading.set(null)},error:()=>{this.downloading.set(null);this.message.set('Download unavailable. Refresh history or retry later.')}})}
}

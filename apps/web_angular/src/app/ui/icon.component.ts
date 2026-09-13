import {Component,Input} from '@angular/core';
@Component({selector:'x-icon',standalone:true,template:`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
 @switch(name){
  @case('dashboard'){<rect x="3" y="3" width="7" height="7" rx="2"/><rect x="14" y="3" width="7" height="7" rx="2"/><rect x="3" y="14" width="7" height="7" rx="2"/><rect x="14" y="14" width="7" height="7" rx="2"/>}
  @case('compress'){<path d="M8 3v4H4M16 3v4h4M8 21v-4H4M16 21v-4h4"/><path d="m9 9 3 3 3-3M12 12v5"/>}
  @case('decompress'){<path d="M8 3H4v4M16 3h4v4M8 21H4v-4M16 21h4v-4"/><path d="m15 15-3-3-3 3M12 12V7"/>}
  @case('history'){<path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5M12 7v5l3 2"/>}
  @case('security'){<path d="M12 3 5 6v5c0 4.6 2.8 8 7 10 4.2-2 7-5.4 7-10V6z"/><path d="m9 12 2 2 4-4"/>}
  @case('user'){<circle cx="12" cy="8" r="4"/><path d="M4 21c.8-4 3.4-6 8-6s7.2 2 8 6"/>}
  @case('share'){<circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><path d="m9 10 6-3M9 14l6 3"/>}
  @case('upload'){<path d="M12 16V4m0 0L7 9m5-5 5 5"/><path d="M4 15v5h16v-5"/>}
  @case('download'){<path d="M12 4v12m0 0 5-5m-5 5-5-5"/><path d="M4 20h16"/>}
  @case('refresh'){<path d="M20 7v5h-5M4 17v-5h5"/><path d="M6.1 8A7 7 0 0 1 18 6l2 6M17.9 16A7 7 0 0 1 6 18l-2-6"/>}
  @case('logout'){<path d="M10 4H5v16h5M14 8l4 4-4 4M18 12H9"/>}
  @case('mail'){<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 7 9 6 9-6"/>}
  @case('phone'){<rect x="7" y="2" width="10" height="20" rx="2"/><path d="M11 18h2"/>}
  @case('key'){<circle cx="8" cy="15" r="4"/><path d="m11 12 8-8m-3 3 3 3"/>}
  @case('check'){<circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/>}
  @case('file'){<path d="M6 2h8l4 4v16H6z"/><path d="M14 2v5h5"/>}
  @case('menu'){<path d="M4 7h16M4 12h16M4 17h16"/>}
  @case('close'){<path d="m6 6 12 12M18 6 6 18"/>}
  @default{<circle cx="12" cy="12" r="9"/>}
 }</svg>`})
export class IconComponent{@Input()name='';}

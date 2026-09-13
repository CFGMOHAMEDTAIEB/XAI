export type Plan={name:string;audience:string;price:string;cta:string;href:string;featured?:boolean;features:string[];note:string};
// Commercial billing is not implemented. Update this catalog when product terms are approved.
export const plans:Plan[]=[
 {name:'Free',audience:'For individuals evaluating XAI-Compress.',price:'Not yet available',cta:'Request access',href:'/contact',features:['Web portal access','Lossless compression workflow','File history and secure downloads','Optional authenticator MFA'],note:'No checkout or usage entitlement is currently implemented.'},
 {name:'Pro',audience:'For professionals with heavier workflows.',price:'Coming later',cta:'Contact us',href:'/contact',featured:true,features:['Planned commercial tier','Terms and limits to be confirmed','No purchase available today'],note:'Features, limits and pricing have not been approved.'},
 {name:'Business',audience:'For teams evaluating organizational use.',price:'Contact',cta:'Discuss requirements',href:'/contact',features:['Requirements consultation','Deployment and support scope to be agreed','No self-service billing'],note:'Team administration is not currently offered as a public product.'},
 {name:'Enterprise',audience:'For organizations with deployment and support requirements.',price:'Custom',cta:'Contact us',href:'/contact',features:['Architecture consultation','Security and deployment review','Commercial terms by agreement'],note:'No SLA or capability is implied until contractually agreed.'}
];

export interface AuthToken{access_token:string;token_type:string}
export interface FileItem{id:number;name:string;sha256:string;original_size:number;compressed_size:number;codec:string;created_at:string;status:string}
export interface ShareResult{share_code:string;expires_at:string;recipient_email:string}
export interface DashboardStats{files:number;savedBytes:number;shares:number;security:string}

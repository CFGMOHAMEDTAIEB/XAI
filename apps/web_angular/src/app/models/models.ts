export interface AuthToken{access_token:string;refresh_token?:string;token_type:string;mfa_enabled:boolean;enrollment_required?:boolean}
export interface FileItem{id:number;name:string;sha256:string;original_size:number;compressed_size:number;codec:string;created_at:string;status:string}
export interface ShareResult{share_code:string;expires_at:string;recipient_email:string;email_delivery:'captured_by_mailpit'|'accepted_by_smtp'|'accepted_by_provider'|'failed'|'not_configured'}
export interface ShareItem{id:number;file_name:string;recipient_email:string;expires_at:string;status:'active'|'expired'|'revoked'|'exhausted';download_count:number;max_downloads:number}
export interface RedeemedShare{file:{name:string;size:number};sender:{name:string;email:string}|null;expires_at:string;remaining_downloads:number;max_downloads:number}
export interface DashboardStats{files:number;savedBytes:number;shares:number;security:string}

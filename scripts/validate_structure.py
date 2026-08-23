from pathlib import Path
required=['apps/desktop_flutter','apps/mobile_authenticator_flutter','apps/web_angular','services/api_fastapi','engines/ai_compression','analytics','packages/protobuf_contracts','infrastructure/keycloak']
missing=[p for p in required if not Path(p).exists()]
if missing: raise SystemExit('Missing: '+', '.join(missing))
print('Structure OK:',len(required),'required modules found')

# XAI Authenticator

Unlock the app with device authentication, then sign in or create an XAI account.
Choose **Setup Authenticator**, enter the verification code sent to your registered
email, and enter the TOTP displayed for that enrollment. The backend creates the
only authoritative secret. The app provisions it directly into platform secure
storage; users do not invent or manually enter Base32 secrets.

Email confirmation releases the pending secret once. MFA becomes enabled only
after TOTP confirmation. Existing saved codes remain available without a backend
session, so they can be used to sign in when MFA is already enabled. Passwords and
access tokens are not persisted; locking or signing out clears the access token.

## Debug validation

The actual configuration key is `String.fromEnvironment('XAI_API_URL')` in
`lib/services/deployment_config.dart`. Both debug and release defaults are
`https://xai-1-be9s.onrender.com`. Release validation still requires public HTTPS.

```powershell
flutter analyze
flutter test
flutter run -d 816f7f5f --dart-define=XAI_API_URL=https://xai-1-be9s.onrender.com
```

Keep `MainActivity : FlutterFragmentActivity()`; local_auth requires it.
Do not regenerate Android platform files over this integration.
No production release should be built until the complete debug flow passes on
the physical phone. Production signing and scanner/email availability must also
be verified separately.

## Recovery

- Storage read failure: retry after unlocking the phone. Existing data is not erased.
- Storage write failure after email verification: retry secure storage; the
  one-time response remains in memory until saved or the page is closed.
- Lost response or app restart before saving: refresh status and explicitly restart
  setup. The previous pending secret becomes invalid. Active MFA is never replaced.
- Wrong/expired email code: resend after 60 seconds. At most five emails per hour.
- Wrong TOTP: use the displayed current code and automatic device time. After five
  incorrect attempts, restart setup. Enrollment expires after 20 minutes.
- Network failure: finite timeout, retry and refresh status. A timed-out request
  may have completed on the backend, so check status before restarting.
- Deleting a local account does not disable backend MFA and may lose account access.

See `services/api_fastapi/MFA_FLOW.md` for the API contract, migration, configuration,
test evidence, and live-validation blockers. No Resend key belongs in Flutter.

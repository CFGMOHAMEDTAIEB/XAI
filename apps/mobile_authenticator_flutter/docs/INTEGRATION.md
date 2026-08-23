# Integration Contract

## Enrollment

Backend response:

```json
{
  "secret": "BASE32_SECRET",
  "otpauth_uri": "otpauth://totp/XAI-Compress:user@example.com?...",
  "qr_png_base64": "..."
}
```

The mobile application scans `otpauth_uri`, validates the scheme and type, and stores the secret in secure storage.

## Confirmation

The mobile code is submitted to:

```text
POST /auth/totp/confirm?code=123456
Authorization: Bearer <access-token>
```

## Login

```json
{
  "email": "user@example.com",
  "password": "user password",
  "totp_code": "123456"
}
```

## Security decisions

- Secrets remain local after enrollment.
- TOTP generation works offline.
- Codes are copied only after explicit user action.
- The backend accepts a small time window for clock drift.
- Device time synchronization is required.

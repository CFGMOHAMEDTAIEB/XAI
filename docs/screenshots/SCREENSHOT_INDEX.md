# XAI-Compress — final visual evidence index

Evidence captured from the real local Flutter Desktop and Mobile applications on 2026-09-20/21, with recipient and measured cross-user evidence completed on 2026-09-25/26. USER 1 is `m.taieb2k@gmail.com`; USER 2 is `mohamed.taieb1@outlook.com`. All listed PNGs were visually inspected for passwords, one-time codes, share codes, tokens, and database credentials. `PASS` means the cited evidence truthfully proves the stated step; it does **not** imply that a different interface or later workflow step passed.

| ID | Filename | Application | User | Step / action | Actual result | Suggested PFE caption | Section | Sensitive-data review | Status |
|---|---|---|---|---|---|---|---|---|---|
| S01 | [02_register_page.png](02_registration/02_register_page.png) | Flutter Desktop | USER 1 | Open registration | Empty registration form | Formulaire de création de compte | Authentification | Clear | PASS |
| S02 | [02_register_user1_email.png](02_registration/02_register_user1_email.png) | Flutter Desktop | USER 1 | Enter permitted email | Email visible, password field empty | Saisie de l'adresse de l'utilisateur | Authentification | Clear | PASS |
| S03 | [02_register_success.png](02_registration/02_register_success.png) | Flutter Desktop | USER 1 | Submit registration | Verification form appears; not a standalone success banner | Passage à la vérification électronique | Authentification | Clear | PASS |
| S04 | [03_email_verification_page.png](03_email_verification/03_email_verification_page.png) | Flutter Desktop | USER 1 | Open verification | Empty code form | Vérification de l'adresse électronique | Authentification | No code visible | PASS |
| S05 | [03_email_verified_success.png](03_email_verification/03_email_verified_success.png) | Flutter Desktop | USER 1 | Submit real code | Returned to login; verified status is corroborated by S29 | Retour à l'authentification après vérification | Authentification | No code visible | PASS |
| S06 | [04_login_page.png](04_login_mfa/04_login_page.png) | Flutter Desktop | USER 1 | Open login | Empty login form | Interface de connexion | Authentification | Clear | PASS |
| S07 | [04_login_user1_masked.png](04_login_mfa/04_login_user1_masked.png) | Flutter Desktop | USER 1 | Fill credentials | Email visible, password masked | Connexion avec mot de passe masqué | Authentification | Password masked | PASS |
| S08 | [04_login_user1.png](04_login_mfa/04_login_user1.png) | Flutter Desktop | USER 1 | Report copy of login form | Same real masked form as S07 | Authentification de l'utilisateur | Authentification | Password masked | PASS |
| S09 | [04_login_result.png](04_login_mfa/04_login_result.png) | Flutter Desktop | USER 1 | Submit login | Authenticated dashboard; MFA not enrolled | Ouverture de l'espace privé | Authentification | Clear | PASS |
| S10 | [04_login_success.png](04_login_mfa/04_login_success.png) | Flutter Desktop | USER 1 | Report copy of login result | Same real dashboard as S09 | Connexion réussie | Authentification | Clear | PASS |
| S11 | [06_compression_page.png](06_compression/06_compression_page.png) | Flutter Desktop | USER 1 | Open compression | Empty file input and Hybrid V3 option | Interface de compression | Compression | Clear | PASS |
| S12 | [06_file_selected.png](06_compression/06_file_selected.png) | Flutter Desktop | USER 1 | Select harmless 305-byte text file | Exact input path displayed | Sélection du fichier de démonstration | Compression | Clear | PASS |
| S13 | [06_compression_ready.png](06_compression/06_compression_ready.png) | Flutter Desktop | USER 1 | Set output path | Input and output paths displayed; button enabled | Préparation de la compression | Compression | Clear | PASS |
| S14 | [06_compression_success.png](06_compression/06_compression_success.png) | Flutter Desktop | USER 1 | Run real compression | Completed; 0.30 KiB to 0.25 KiB, Hybrid V3 displayed | Compression réussie par le moteur hybride | Compression | Clear | PASS |
| S15 | [08_share_page.png](08_sharing/08_share_page.png) | Flutter Desktop | USER 1 | Open Shares | Owned-file, recipient and expiry controls; prior share row visible | Interface de partage sécurisé | Partage | No share code visible | PASS |
| S16 | [08_share_recipient_user2.png](08_sharing/08_share_recipient_user2.png) | Flutter Desktop | USER 1 | Enter recipient | Demo file selected; USER 2 email field horizontally clipped | Sélection du destinataire du partage | Partage | No share code visible | PASS |
| S17 | [10_decompression_page.png](10_decompression/10_decompression_page.png) | Flutter Desktop | USER 1 | Open decompression | Empty verified-decompression form | Interface de décompression | Décompression | Clear | PASS |
| S18 | [10_compressed_file_selected.png](10_decompression/10_compressed_file_selected.png) | Flutter Desktop | USER 1 | Select an earlier `.xaic` | Earlier artifact path displayed; **not** the final verified round-trip artifact | Sélection d'une archive compressée | Décompression | Clear; exclude from round-trip proof | PASS |
| S19 | [10_decompression_success.png](10_decompression/10_decompression_success.png) | Flutter Desktop | USER 1 | Decompress unique round-trip artifact | Completed; 305-byte restored file | Décompression réussie du fichier de démonstration | Décompression | Clear | PASS |
| S20 | [10_sha256_verification.png](10_decompression/10_sha256_verification.png) | Notepad / measured JSON | Technical | Inspect hash evidence | Original and restored SHA-256 equal | Vérification de l'intégrité par SHA-256 | Validation | No credentials or tokens | PASS |
| S21 | [11_desktop_login.png](11_desktop/11_desktop_login.png) | Flutter Desktop | Public | Open client | Empty login screen | Interface de l'application de bureau | Clients | Clear | PASS |
| S22 | [11_desktop_dashboard.png](11_desktop/11_desktop_dashboard.png) | Flutter Desktop | USER 1 | Open dashboard | Authenticated private workspace | Tableau de bord de l'application de bureau | Clients | Clear | PASS |
| S23 | [11_desktop_compression.png](11_desktop/11_desktop_compression.png) | Flutter Desktop | USER 1 | Open compressor | Input and output controls | Fonction de compression sur Windows | Clients | Clear | PASS |
| S24 | [11_desktop_decompression.png](11_desktop/11_desktop_decompression.png) | Flutter Desktop | USER 1 | Open decompressor | Verified-decompression controls | Fonction de décompression sur Windows | Clients | Clear | PASS |
| S25 | [11_desktop_history.png](11_desktop/11_desktop_history.png) | Flutter Desktop | USER 1 | Open history before operation | “No server operations yet” at capture time | Historique initial du compte | Clients | Clear; not post-compression history | PASS |
| S26 | [11_desktop_recovery_view.png](11_desktop/11_desktop_recovery_view.png) | Flutter Desktop | USER 1 | Open normal recovery | Reset request form | Récupération normale du compte | Authentification | Clear | PASS |
| S27 | [11_desktop_reset_code_step.png](11_desktop/11_desktop_reset_code_step.png) | Flutter Desktop | USER 1 | Request reset | Empty reset-code form | Étape de vérification du changement de mot de passe | Authentification | No code visible | PASS |
| S28 | [11_desktop_resumed_state.png](11_desktop/11_desktop_resumed_state.png) | Flutter Desktop | Public | Relaunch client | Empty login form after stack restart | Redémarrage de l'application de bureau | Clients | Clear | PASS |
| S29 | [11_desktop_security.png](11_desktop/11_desktop_security.png) | Flutter Desktop | USER 1 | Open Security | Account active, email verified, authenticator not enabled | État de sécurité du compte | Sécurité | No seed or secret | PASS |
| S30 | [12_mobile_launch.png](12_mobile/12_mobile_launch.png) | Flutter Mobile on Android 17 | Device | Launch app | Genuine Flutter splash screen | Lancement de l'application mobile | Authentificateur | Clear | PASS |
| S31 | [12_mobile_home.png](12_mobile/12_mobile_home.png) | Flutter Mobile on Android 17 | Signed out | Open landing page | XAI secure identity landing with Create account and Login | Accueil de l'authentificateur mobile | Authentificateur | Clear | PASS |
| S32 | [12_mobile_login.png](12_mobile/12_mobile_login.png) | Flutter Mobile on Android 17 | Signed out | Open login | Empty real login form | Connexion depuis l'application mobile | Authentificateur | No password entered | PASS |
| S33 | [12_mobile_biometric_gate.png](12_mobile/12_mobile_biometric_gate.png) | Flutter Mobile on Android 17 | Device | Open protected local vault | Local biometrics/device-credential gate | Protection locale de l'authentificateur | Authentificateur | No TOTP visible | PASS |
| S34 | [12_mobile_secure_storage_error.png](12_mobile/12_mobile_secure_storage_error.png) | Flutter Mobile on Android 17 | Device | First secure-storage attempt | Retry screen before the emulator stabilized | Diagnostic de stockage sécurisé | Technique | Clear; exclude from report | PASS |
| S35 | [12_mobile_retry_result.png](12_mobile/12_mobile_retry_result.png) | Flutter Mobile on Android 17 | Device | Retry secure storage | Same local-authentication gate as S33 | Nouvelle tentative d'accès local | Technique | No TOTP visible; duplicate | PASS |
| S36 | [12_mobile_unlock_prompt.png](12_mobile/12_mobile_unlock_prompt.png) | Flutter Mobile on Android 17 | Device | Attempt unlock without device credential | Authentication not completed | Échec contrôlé sans identifiant local configuré | Technique | No PIN/TOTP visible; exclude from report | PASS |
| S37 | [12_mobile_device_prompt.png](12_mobile/12_mobile_device_prompt.png) | Android secure surface | Device | Device-authentication prompt | Android secure window renders black in screenshot | Surface protégée par Android | Technique | No PIN/TOTP visible; not report-ready | PASS |
| S38 | [09_user2_registration.png](09_recipient/09_user2_registration.png) | Flutter Mobile | USER 2 | Fill registration form | USER 2 identity visible and both password fields masked; backend registration success is operational evidence, not shown by this image | Préparation du compte destinataire | Partage | Passwords masked | PASS |
| S39 | [09_login_user2.png](09_recipient/09_login_user2.png) | Flutter Desktop | USER 2 | Fill login form | USER 2 email visible and password masked; successful authentication was verified through the local backend, not this desktop instance | Authentification du destinataire | Partage | Password masked | PASS |
| S40 | [10_user1_user2_sha256_verification.png](10_decompression/10_user1_user2_sha256_verification.png) | Generated technical evidence | USER 1 → USER 2 | Compare preserved files | Direct measurements show 305 → 257 → 305 bytes and equal original/restored SHA-256 | Vérification d'intégrité inter-utilisateurs | Validation | Explicitly labeled non-UI; no secrets | PASS |
| S41 | [12_mobile_user2_registration.png](12_mobile/12_mobile_user2_registration.png) | Flutter Mobile on Android 17 | Signed out | Open registration | Genuine empty mobile registration form; no account completion claimed by this image | Formulaire mobile de création de compte | Authentification | Clear; not report-ready | PASS |

## Report-ready mapping

The following source images have byte-identical clean copies in `report_ready/`. Every other source screenshot listed above is **not** report-ready.

| Source evidence | Report-ready copy |
|---|---|
| S02 | `fig_registration.png` |
| S03 / S04 | `fig_email_verification.png` |
| S06 / S21 | `fig_desktop.png` |
| S07 / S08 | `fig_login.png` |
| S09 / S10 / S22 | `fig_dashboard.png` |
| S11 / S23 | `fig_compression.png` |
| S14 | `fig_compression_success.png` |
| S16 | `fig_share_recipient.png` |
| S19 | `fig_decompression.png` |
| S20 | `fig_sha256_roundtrip.png` |
| S29 | `fig_security_validation.png` |
| S31 | `fig_mobile_home.png` |
| S33 / S35 | `fig_mobile_authenticator.png` |
| S38 | `fig_user2_registration.png` |
| S39 | `fig_user2_login.png` |
| S40 | `fig_user1_user2_sha256.png` |

## Evidence limits

- On 2026-09-26, Angular, Next.js, Downloads, .NET Admin, pgAdmin, and Mailpit all returned HTTP 200, while PostgreSQL accepted TCP connections on port 15432. Their screenshots remain `BLOCKED`: the supported browser-control runtime reported `No browser is available` and listed no connected browser instances.
- USER 1 authenticator enrollment remains `NOT_PROVEN`. S29 explicitly shows that authenticator MFA is not enabled. Mobile screenshots prove launch and local device protection only.
- The share-success dialog was not saved because it displayed a one-time bearer code. Share creation, redemption, and authorized download were nevertheless verified through the real local backend; no bearer code was retained.
- USER 2 backend authentication succeeded, but a successful USER 2 desktop session is `NOT_PROVEN`: the captured desktop build targeted the remote production API. S39 is therefore only a genuine masked login-form capture.
- USER 2 decompression was completed by the same repository engine command used beneath the desktop workflow. No clean application success window survives, so no application screenshot was fabricated.
- S40 is deliberately labeled **technical evidence — not an application UI capture**. Its source values are [share_roundtrip.json](evidence/share_roundtrip.json) and direct measurements of the preserved files.
- The earlier `demo_xai_compress.xaic` restored `README.md` and was excluded from both passing measurements. No token, password, TOTP, verification code, or share code is stored in this directory.

## Final acceptance matrix

| STEP | USER | INTERFACE | EVIDENCE | RESULT |
|---|---|---|---|---|
| USER 1 registration | USER 1 | Flutter Desktop | S01–S03 | PASS |
| USER 1 verification | USER 1 | Flutter Desktop / backend | S04–S05 and verified state in S29 | PASS |
| USER 1 login | USER 1 | Flutter Desktop | S06–S10 | PASS |
| USER 1 compression | USER 1 | Flutter Desktop / engine | S11–S14; 305-byte source to 257-byte archive | PASS |
| USER 1 decompression | USER 1 | Flutter Desktop / engine | S17, S19; restored size 305 bytes | PASS |
| USER 1 SHA-256 | USER 1 | Technical measurement | S20 and `evidence/roundtrip.json` | PASS |
| USER 2 registration | USER 2 | Flutter Mobile / local FastAPI | S38 plus completed backend contract | PASS |
| USER 2 verification | USER 2 | Local FastAPI / verification mail | Completed backend verification; GUI email capture unavailable | PASS |
| USER 2 login | USER 2 | Local FastAPI | Successful backend login; S39 shows only the masked desktop form | PASS |
| Share creation | USER 1 | Flutter Desktop / local FastAPI | S15–S16 plus completed fresh-share response; bearer code not retained | PASS |
| Share redemption | USER 2 | Local FastAPI | Real recipient redemption completed | PASS |
| Authorized download | USER 2 | Local FastAPI | Preserved `evidence/user2_received_demo.xaic`, 257 bytes | PASS |
| USER 2 decompression | USER 2 | Repository engine CLI | Preserved `evidence/user2_restored_demo.txt`, 305 bytes | PASS |
| USER1 → USER2 SHA-256 | USER 1 → USER 2 | Direct file measurement | S40 and `evidence/share_roundtrip.json`; hashes equal | PASS |
| Mobile launch | Device | Flutter Mobile on Android 17 | S30–S33 | PASS |
| Authenticator enrollment | USER 1 | Flutter Desktop / Mobile | S29 says not enabled; no USER 1 enrollment demonstrated | NOT_PROVEN |
| Next.js screenshots | Public | Browser | No controllable browser | BLOCKED |
| Angular screenshots | USER 1 / USER 2 | Browser | No controllable browser | BLOCKED |
| .NET Admin screenshots | Admin | Browser | No controllable browser | BLOCKED |
| pgAdmin screenshots | Technical | Browser | No controllable browser | BLOCKED |
| Mailpit screenshots | USER 1 / USER 2 | Browser | Message metadata only; no secret-safe GUI capture | BLOCKED |

## Current image inventory

Primary evidence counts exclude the duplicate copies in `report_ready/`.

| Category | Actual PNG/JPG count |
|---|---:|
| Desktop | 29 |
| Mobile | 10 |
| Angular | 0 |
| Next.js | 0 |
| .NET Admin | 0 |
| pgAdmin / database | 0 |
| Mailpit | 0 |
| Technical evidence | 2 |
| Report-ready copies | 16 |

## Component evidence matrix

| COMPONENT | REQUIRED EVIDENCE | CAPTURED | STATUS |
|---|---|---|---|
| Flutter Desktop | Registration, verification, login, dashboard, compression, decompression, sharing, security | Yes | PASS |
| Flutter Mobile | Launch, home, login, local authenticator lock | Yes | PASS |
| Angular Portal | Genuine browser pages | No | BLOCKED |
| Next.js Public | Home, downloads, public status if implemented | No | BLOCKED |
| .NET Admin | Genuine implemented admin pages | No | BLOCKED |
| PostgreSQL/pgAdmin | Safe schema/table views | No | BLOCKED |
| Mailpit | Inbox and safe message metadata | No | BLOCKED |
| USER 1 compression | Source selection and completed compression | Yes | PASS |
| USER 1 decompression | Completed decompression | Yes | PASS |
| USER 1 SHA-256 | Measured original/restored equality | Yes | PASS |
| Share creation | Share form and recipient | Yes | PASS |
| USER 2 registration | Genuine filled form plus backend completion | Yes | PASS |
| USER 2 login | Masked form only; backend login passed but no successful UI state | Partial | NOT_PROVEN |
| USER 2 share receipt | Recipient UI | No | NOT_PROVEN |
| USER 2 download | Authorized-download UI | No | NOT_PROVEN |
| USER 2 decompression | Application success UI | No; engine result only | NOT_PROVEN |
| Cross-user SHA-256 | Sanitized measured technical evidence | Yes | PASS |
| Authenticator enrollment | Safe enrolled-device and enabled-MFA states | No | NOT_PROVEN |

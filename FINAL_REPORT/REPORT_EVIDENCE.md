# REPORT EVIDENCE

## Analyse de Rapport Houssem

Référence: `rapport-pfe/Rapport_PFE_Saada_HoussemEddine.pdf`, 113 pages. Structure observée: couverture et autorisation de dépôt; dédicace; remerciements; table des matières; listes des figures et tableaux; introduction générale; cinq chapitres avec introduction/conclusion; conclusion générale; bibliographie. Le rapport compte de nombreuses figures et tables et suit une numérotation académique. Cette structure a guidé le front matter, la progression, les légendes et les conclusions; aucun texte projet n’a été copié.

## Matrice des affirmations

| Affirmation | Preuve | Confiance |
|---|---|---|
| 43 routes REST observées | `services/api_fastapi/app/main.py; account.py; mfa.py; authenticator.py` | VERIFIED FROM SOURCE |
| 12 tables SQLAlchemy | `services/api_fastapi/app/models.py` | VERIFIED FROM SOURCE |
| Fail-closed ClamAV/YARA | `app/security_scanner.py; tests/test_security_scanner.py; test_product_truth.py` | VERIFIED FROM SOURCE/TEST |
| Refresh tokens hachés et révocables | `models.py; security.py; main.py` | VERIFIED FROM SOURCE |
| MFA TOTP et enrôlement | `mfa.py; authenticator.py; mobile lib/core/app_state.dart` | VERIFIED FROM SOURCE |
| Hybrid V3 top-3 retenu | `engines/XAI-Compress/results/hybrid_v3/final_report.md` | HISTORICAL AUTHORITATIVE ARTIFACT |
| 140 fichiers, 368446658 octets | `engines/XAI-Compress/results/hybrid_v3/final_report.md` | HISTORICAL AUTHORITATIVE ARTIFACT |
| Brotli-11 plus compact que V3 | `engines/XAI-Compress/results/hybrid_v3/final_report.md` | HISTORICAL AUTHORITATIVE ARTIFACT |
| Vercel + Render configurés | `deployment/README.md; app configs` | VERIFIED FROM CONFIG; LIVE NOT PROVEN |
| Mobile secure storage/biométrie | `mobile services/secure_account_store.dart; biometric_service.dart` | VERIFIED FROM SOURCE |
| Angular refresh sérialisé | `apps/web_angular source and product truth audit` | VERIFIED FROM SOURCE |
| Admin lecture utilisateurs/jobs/audit | `apps/admin_dotnet; API admin routes` | VERIFIED FROM SOURCE |
| Production prête | `Aucune preuve E2E complète` | NOT VERIFIED / DO NOT CLAIM |
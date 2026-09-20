# SCREENSHOT CHECKLIST

Ne jamais afficher OTP, secret TOTP, token, mot de passe, clé API, chaîne de base ou e-mail réel.

| ID | Application | Écran | Étapes | Visible | À masquer | Légende | Chapitre | Priorité |
|---|---|---|---|---|---|---|---:|---|
| MOBILE-01 | Mobile | Création de compte | Ouvrir Inscription | Champs non remplis et bouton | E-mail, mots de passe | Création de compte | 9 | MANDATORY |
| MOBILE-02 | Mobile | Vérification e-mail | Soumettre inscription | Écran code et renvoi | Code et adresse réelle | Vérification de l’adresse | 9 | MANDATORY |
| MOBILE-03 | Mobile | Enrôlement TOTP | Après vérification | Instructions et statut | QR, secret, OTP | Enrôlement authentificateur | 9 | MANDATORY |
| MOBILE-04 | Mobile | Code circulaire | Déverrouiller | Compte fictif et anneau | OTP, e-mail | Code TOTP rotatif | 9 | RECOMMENDED |
| DESKTOP-01 | Desktop | Compression cloud | Connexion puis Compression | Fichier test, mode, statut | Chemin personnel, token | Compression depuis Desktop | 10 | MANDATORY |
| DESKTOP-02 | Desktop | Résultat | Terminer compression | Tailles, codec, SHA masqué | Chemins, empreinte complète | Résultat de compression | 10 | MANDATORY |
| ANGULAR-01 | Angular | Tableau de bord | Connexion portail | Indicateurs et navigation | E-mail personnel | Tableau de bord utilisateur | 11 | MANDATORY |
| ANGULAR-02 | Angular | Compression | Route /compress | Sélecteur, mode, action | Token, fichier privé | Lancement de compression | 11 | MANDATORY |
| ANGULAR-03 | Angular | Historique | Route /history | Table et actions | Noms privés | Historique des opérations | 11 | RECOMMENDED |
| ADMIN-01 | Admin | Dashboard | Connexion admin test | Mesures et état | Comptes réels | Tableau de bord administratif | 13 | MANDATORY |
| ADMIN-02 | Admin | Audit | Ouvrir Audit | Actions assainies | Détails sensibles | Journal d’audit | 13 | RECOMMENDED |
| PUBLIC-01 | Next.js | Accueil | Ouvrir racine | Architecture et CTA | Données démo obsolètes | Site public | 12 | RECOMMENDED |
| TEST-01 | Terminal | Tests backend | Exécuter pytest ciblé | Résumé succès | Chemins/variables | Suite backend | 16 | MANDATORY |
| TEST-02 | Terminal | Tests moteur | Exécuter pytest moteur | Résumé et skips | Chemins personnels | Suite moteur | 16 | MANDATORY |
| TEST-03 | Docker | Services sains | docker compose ps | Health states | Secrets/env | Services Docker | 15 | MANDATORY |
| SEC-01 | Terminal | Validation scanner | Diagnostic contrôlé | ClamAV/YARA ready | Règles privées | Validation scanners | 8 | MANDATORY |
| DEPLOY-01 | Vercel/Render | Déploiements | Ouvrir dashboards | Services et dates | IDs/tokens/logs | Déploiements déclarés | 15 | RECOMMENDED |
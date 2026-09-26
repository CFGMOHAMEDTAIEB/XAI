# Parcours utilisateur PFE — état observé

Ce récit sépare les captures d'interface des preuves techniques et opérationnelles. USER 1 est `m.taieb2k@gmail.com` et USER 2 est `mohamed.taieb1@outlook.com`. Aucun mot de passe, jeton, code de vérification, secret TOTP ou code de partage n'est conservé dans ce dossier.

## 1. Cycle local de USER 1

| Ordre | Étape | Preuve | Résultat |
|---|---|---|---|
| 1 | Inscription de USER 1 | [Formulaire](02_registration/02_register_page.png), [adresse saisie](02_registration/02_register_user1_email.png), [passage à la vérification](02_registration/02_register_success.png) | PASS |
| 2 | Vérification de l'adresse | [Écran de vérification](03_email_verification/03_email_verification_page.png), [retour à la connexion](03_email_verification/03_email_verified_success.png), [état Verified](11_desktop/11_desktop_security.png) | PASS |
| 3 | Connexion de USER 1 | [Identifiants masqués](04_login_mfa/04_login_user1.png), [tableau de bord authentifié](04_login_mfa/04_login_success.png) | PASS |
| 4 | Validation de sécurité | [État du compte](11_desktop/11_desktop_security.png) : adresse vérifiée, authentificateur non activé | PASS |
| 5 | Sélection du fichier source | [Fichier sélectionné](06_compression/06_file_selected.png), [mesure initiale](evidence/demo_file.json) : 305 octets | PASS |
| 6 | Compression | [Préparation](06_compression/06_compression_ready.png), [résultat Hybrid V3](06_compression/06_compression_success.png) : 305 → 257 octets | PASS |
| 7 | Décompression locale | [Résultat Desktop](10_decompression/10_decompression_success.png) : fichier restauré de 305 octets | PASS |
| 8 | Vérification SHA-256 locale | [Vue technique](10_decompression/10_sha256_verification.png), [valeurs exactes](evidence/roundtrip.json) : original = restauré | PASS |

Le contrôle ClamAV et le contrôle YARA ne possèdent pas de capture distincte. La mention « Scanner-backed » du tableau de bord n'est pas utilisée comme preuve d'un scan du fichier.

## 2. Cycle de partage entre deux utilisateurs

| Ordre | Étape | Preuve | Résultat |
|---|---|---|---|
| 1 | Artefact compressé de USER 1 | Archive réelle de 257 octets issue du cycle vérifié | PASS |
| 2 | Création du partage USER 1 → USER 2 | [Interface de partage](08_sharing/08_share_page.png), [destinataire saisi](08_sharing/08_share_recipient_user2.png), puis réponse réelle du backend local | PASS |
| 3 | Inscription de USER 2 | [Formulaire USER 2](09_recipient/09_user2_registration.png) et inscription réussie par le contrat réel du backend | PASS |
| 4 | Vérification de USER 2 | Vérification électronique réussie par le backend ; aucun code conservé | PASS |
| 5 | Connexion de USER 2 | Connexion au backend local réussie ; [formulaire Desktop masqué](09_recipient/09_login_user2.png). Une session Desktop réussie n'est pas revendiquée, car cette version ciblait l'API distante | PASS |
| 6 | Rédemption du partage | Rédemption réelle par USER 2 avec le backend local ; code porteur effacé ensuite | PASS |
| 7 | Téléchargement autorisé | Fichier préservé `evidence/user2_received_demo.xaic`, 257 octets | PASS |
| 8 | Décompression par USER 2 | Moteur réel du dépôt ; fichier préservé `evidence/user2_restored_demo.txt`, 305 octets. Aucune capture d'application n'a été fabriquée | PASS |
| 9 | Vérification inter-utilisateurs | [Preuve technique explicitement étiquetée](10_decompression/10_user1_user2_sha256_verification.png) et [mesures structurées](evidence/share_roundtrip.json) | PASS |

Mesure finale : `SHA256(USER 1 original) = SHA256(USER 2 restored) = 1b8302a372a817388db1c5569c2d61d12cea8dee2d220cd00eb9bb7d7d1540f6`. Les tailles sont 305 → 257 → 305 octets.

Le dialogue de succès du partage n'a pas été sauvegardé parce qu'il affichait un code porteur à usage unique. La réception, le téléchargement et la décompression sont prouvés par les fichiers et les opérations réelles, mais pas par des captures d'interface USER 2.

## 3. Authentificateur mobile

| Étape | Preuve | Résultat |
|---|---|---|
| Lancement sur émulateur Android 17 | [Splash Flutter](12_mobile/12_mobile_launch.png) | PASS |
| Accueil et connexion | [Accueil](12_mobile/12_mobile_home.png), [formulaire de connexion](12_mobile/12_mobile_login.png) | PASS |
| Protection locale | [Barrière biométrique / identifiant appareil](12_mobile/12_mobile_biometric_gate.png) | PASS |
| Inscription de l'authentificateur pour USER 1 | [État Desktop](11_desktop/11_desktop_security.png) indique « Not enabled » ; aucune inscription USER 1 n'a été démontrée | NOT_PROVEN |

Le profil déjà présent dans l'émulateur appartient à une identité de test différente. Aucun code TOTP ni aucune approbation USER 1 n'est revendiqué.

## Interfaces sans capture

| Interface | État | Motif |
|---|---|---|
| Next.js et téléchargements | BLOCKED | Les deux pages répondent HTTP 200, mais le navigateur contrôlable a répondu `No browser is available`. |
| Angular | BLOCKED | Le portail répond HTTP 200 ; aucun navigateur contrôlable n'est connecté. |
| .NET Admin | BLOCKED | La page de connexion répond HTTP 200 ; aucun navigateur contrôlable n'est connecté. |
| pgAdmin | BLOCKED | La page de connexion répond HTTP 200 et PostgreSQL accepte les connexions TCP ; aucune capture sûre n'est possible sans navigateur contrôlable. |
| Mailpit | BLOCKED | L'interface répond HTTP 200 ; aucune capture GUI sûre n'est possible sans navigateur contrôlable. |

Les visuels retenus figurent dans [report_ready](report_ready/). L'[index](SCREENSHOT_INDEX.md) décrit chaque preuve et ses limites.

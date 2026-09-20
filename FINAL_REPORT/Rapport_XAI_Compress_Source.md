# Rapport XAI-Compress Final

> Version factuelle générée à partir du dépôt. Les champs institutionnels et captures restent à compléter.

# Introduction générale

*Introduction du chapitre.* Les affirmations sont rattachées au code, aux tests, aux configurations ou aux artefacts historiques.

## Contexte et problématique

La croissance des données accentue simultanément les coûts de stockage, le temps de transfert et la surface d’attaque liée au traitement des fichiers. Une plate-forme de compression moderne ne peut donc être évaluée sur le seul taux de réduction: elle doit préserver exactement les octets, borner les ressources, contrôler les contenus hostiles et offrir un parcours cohérent sur plusieurs clients. La problématique retenue est la suivante: comment concevoir une plate-forme multi-client capable de sélectionner une stratégie de compression sans perte selon les caractéristiques d’un fichier, tout en assurant intégrité, authentification forte, analyse antimalware et traçabilité, avec des résultats reproductibles et sans transformer une meilleure vitesse en prétention infondée de meilleure compression?

**Lecture d’ingénierie.** Exactitude, confiance, coût et preuve sont distingués; une configuration n’est pas une preuve de production.

## Objectifs et méthode

XAI-Compress articule un site public Next.js, un portail Angular, un client Flutter Desktop, un authentificateur Flutter, une administration Blazor .NET et une API FastAPI. L’audit suit une méthode de preuve: lecture du code, rapprochement des configurations, inspection des migrations, analyse des tests et confrontation aux rapports de benchmark. Les faits sont marqués comme vérifiés, historiques, proposés ou manquants. Cette discipline est indispensable lorsque l’architecture déclarée excède ce qui a été validé en production.

**Lecture d’ingénierie.** Exactitude, confiance, coût et preuve sont distingués; une configuration n’est pas une preuve de production.

## Organisation du mémoire

Les chapitres progressent de l’état de l’art et des exigences vers l’architecture, l’implémentation, l’IA, la sécurité et les clients. Ils se terminent par le DevOps, les tests, les résultats, les difficultés et les perspectives. Les annexes consolident les endpoints, variables sans valeurs, tables, preuves et captures à produire.

**Lecture d’ingénierie.** Exactitude, confiance, coût et preuve sont distingués; une configuration n’est pas une preuve de production.

## Conclusion du chapitre

Les résultats et limites sont conservés explicitement.

# Chapitre 1 — Contexte et état de l’art

*Introduction du chapitre.* Les affirmations sont rattachées au code, aux tests, aux configurations ou aux artefacts historiques.

## Fondements de la compression

La compression sans perte exploite la redondance statistique sans modifier le message reconstruit. Huffman affecte des mots courts aux symboles fréquents; LZ77 et LZ78 décrivent des répétitions par références; LZW construit un dictionnaire; DEFLATE associe LZ77 et Huffman; gzip et ZIP ajoutent des conteneurs et métadonnées; LZMA recherche des ratios élevés au prix d’un calcul plus important. Aucun algorithme ne domine universellement: les médias déjà compressés, les petits fichiers et les données quasi aléatoires déplacent le compromis entre en-tête, ratio, mémoire et latence.

**Lecture d’ingénierie.** Exactitude, confiance, coût et preuve sont distingués; une configuration n’est pas une preuve de production.

## Modélisation neuronale et codage entropique

Un modèle causal byte-level estime p(x_t|x_{<t}) sur 256 valeurs. La cross-entropie moyenne, exprimée en bits par octet, approche le coût idéal d’un code entropique, mais le conteneur réel ajoute modèle, métadonnées, checksums et alignement. La GRU utilise une porte de mise à jour z_t, une porte de réinitialisation r_t et un état h_t; elle réduit le problème de gradient par rapport au RNN simple, avec moins de paramètres qu’une LSTM. La décompression impose exactement le même modèle, le même checkpoint et le même ordre numérique.

**Lecture d’ingénierie.** Exactitude, confiance, coût et preuve sont distingués; une configuration n’est pas une preuve de production.

## Positionnement XAI

Le nom XAI-Compress ne correspond pas, dans le code audité, à une méthode complète d’explicabilité locale de type SHAP appliquée à chaque octet. La dimension explicable réside surtout dans le sélecteur de codecs, les caractéristiques observables, les routes top-3, les rapports d’ablation et la traçabilité des décisions. Cette interprétation limitée est plus fidèle que l’affirmation d’une IA intrinsèquement explicable.

**Lecture d’ingénierie.** Exactitude, confiance, coût et preuve sont distingués; une configuration n’est pas une preuve de production.

## Comparaison critique

Les solutions classiques sont matures, portables et souvent plus compactes. L’approche hybride vise surtout un routage adaptatif et un meilleur compromis de débit. Les mesures V3 montrent précisément cette nuance: Hybrid V3 est beaucoup plus rapide que Brotli-11 sur le corpus retenu, mais produit un artefact légèrement plus grand. La contribution scientifique tient donc à la sélection contrôlée, au protocole de comparaison et à l’intégration sécurisée, non à une victoire universelle sur Brotli.

**Lecture d’ingénierie.** Exactitude, confiance, coût et preuve sont distingués; une configuration n’est pas une preuve de production.

## Conclusion du chapitre

Les résultats et limites sont conservés explicitement.

# Chapitre 2 — Analyse et spécification des besoins

*Introduction du chapitre.* Les affirmations sont rattachées au code, aux tests, aux configurations ou aux artefacts historiques.

## Acteurs et responsabilités

L’utilisateur standard crée un compte, vérifie son adresse, active éventuellement le MFA, compresse, décompresse, télécharge, consulte l’historique et partage. L’administrateur observe utilisateurs, fichiers, scanner et événements sans qu’une interface visible ne remplace l’autorisation serveur. L’authentificateur mobile provisionne et protège le facteur TOTP. Les services externes comprennent la messagerie, PostgreSQL et les scanners.

**Lecture d’ingénierie.** Exactitude, confiance, coût et preuve sont distingués; une configuration n’est pas une preuve de production.

## Exigences fonctionnelles

Les préconditions critiques sont l’identité validée, l’autorisation sur la ressource, la taille admissible et la disponibilité des scanners. Chaque opération produit un résultat vérifiable ou une erreur non ambiguë. Un partage est lié à un destinataire, une expiration, un nombre de téléchargements et une révocation. La décompression ne doit jamais publier un contenu avant validation du conteneur et contrôle antimalware.

**Lecture d’ingénierie.** Exactitude, confiance, coût et preuve sont distingués; une configuration n’est pas une preuve de production.

## Exigences non fonctionnelles

La confidentialité des secrets, l’intégrité SHA-256, le fail-closed, les limites de ressources, l’audit, la maintenabilité par composants, la portabilité des clients et la reproductibilité des benchmarks forment les exigences structurantes. La disponibilité n’autorise pas l’abaissement silencieux des contrôles. La scalabilité est aujourd’hui limitée par le traitement local et le stockage configuré; l’objet storage et la file distribuée restent des perspectives.

**Lecture d’ingénierie.** Exactitude, confiance, coût et preuve sont distingués; une configuration n’est pas une preuve de production.

## Conclusion du chapitre

Les résultats et limites sont conservés explicitement.

# Chapitre 3 — Architecture globale

*Introduction du chapitre.* Les affirmations sont rattachées au code, aux tests, aux configurations ou aux artefacts historiques.

## Architecture logique

Tous les clients communiquent avec FastAPI par REST. L’API concentre validation, identité, autorisation et orchestration; SQLAlchemy isole la persistance; le moteur est invoqué derrière une frontière de service; les scanners forment une barrière avant et après transformation. Ce découplage évite que les clients manipulent des chemins serveur ou des secrets de base de données.

**Lecture d’ingénierie.** Exactitude, confiance, coût et preuve sont distingués; une configuration n’est pas une preuve de production.

## Flux et frontières de confiance

Le poste client, Internet, la terminaison TLS, l’API, le réseau Docker, la base et le stockage sont des zones distinctes. Un nom de fichier et un MIME sont non fiables; l’identité portée par un JWT est vérifiée mais l’autorisation doit encore contrôler le propriétaire. Les sorties du moteur ne deviennent pas sûres par leur seule provenance: elles sont bornées, vérifiées et rescannées.

**Lecture d’ingénierie.** Exactitude, confiance, coût et preuve sont distingués; une configuration n’est pas une preuve de production.

## Architecture physique et déploiement

Les configurations prévoient Vercel pour les frontends et Render pour les services applicatifs, tandis que Compose assemble le développement avec PostgreSQL, ClamAV et Mailpit. Ce rapport distingue la topologie définie du déploiement effectivement prouvé: aucune disponibilité de production n’est déduite d’un fichier de configuration.

**Lecture d’ingénierie.** Exactitude, confiance, coût et preuve sont distingués; une configuration n’est pas une preuve de production.

## Conclusion du chapitre

Les résultats et limites sont conservés explicitement.

# Chapitre 4 — Backend FastAPI

*Introduction du chapitre.* Les affirmations sont rattachées au code, aux tests, aux configurations ou aux artefacts historiques.

## Organisation et contrats REST

Les modules main.py, account.py, mfa.py et authenticator.py enregistrent 43 routes observées. Pydantic valide les entrées; les dépendances FastAPI extraient l’utilisateur; SQLAlchemy gère les unités de travail. Les réponses publiques d’état sont volontairement assainies. CORS dépend d’une liste d’origines et les tests couvrent le rejet d’une origine non autorisée.

**Lecture d’ingénierie.** Exactitude, confiance, coût et preuve sont distingués; une configuration n’est pas une preuve de production.

## Cycle d’identité

L’inscription hache le mot de passe et crée un compte non vérifié. La vérification e-mail utilise un code haché, borné en tentatives et en expiration. La connexion vérifie les identifiants puis le MFA selon la politique. Le JWT d’accès est court; le refresh token n’est persisté que sous forme de hachage et peut être révoqué. L’oubli de mot de passe sépare demande, vérification de code et remplacement, ce qui réduit la durée d’exposition d’un jeton de réinitialisation.

**Lecture d’ingénierie.** Exactitude, confiance, coût et preuve sont distingués; une configuration n’est pas une preuve de production.

## Traitement de fichiers et erreurs

Le téléversement est copié sous limites, haché, scanné puis transmis au moteur. Les erreurs internes sont traduites sans exposer chemins ni commandes. L’historique est filtré par propriétaire; l’administration utilise un contrôle de rôle. Les migrations 003/004 et leur runner sont testés, notamment pour maintenir l’alignement de audit_events et de son updated_at.

**Lecture d’ingénierie.** Exactitude, confiance, coût et preuve sont distingués; une configuration n’est pas une preuve de production.

## Conclusion du chapitre

Les résultats et limites sont conservés explicitement.

# Chapitre 5 — Base de données

*Introduction du chapitre.* Les affirmations sont rattachées au code, aux tests, aux configurations ou aux artefacts historiques.

## Modèle conceptuel

Le noyau lie users aux fichiers, tokens, défis, dispositifs et événements. files conserve tailles, codec, empreinte, chemins internes, statut et preuve d’intégrité. share_codes relie fichier, émetteur et destinataire sans stocker le code en clair. audit_events et auth_events séparent l’audit fonctionnel de la chronologie d’authentification.

**Lecture d’ingénierie.** Exactitude, confiance, coût et preuve sont distingués; une configuration n’est pas une preuve de production.

## Contraintes et données sensibles

Les e-mails, identifiants de dispositif et hachages de tokens sont indexés ou uniques selon leur rôle. Les secrets TOTP sont sensibles et ne doivent jamais apparaître dans les logs; le code actuel nécessite leur disponibilité serveur pour valider le facteur, sans preuve d’un chiffrement applicatif au repos. Les chemins d’artefacts sont internes et ne constituent pas des URL publiques.

**Lecture d’ingénierie.** Exactitude, confiance, coût et preuve sont distingués; une configuration n’est pas une preuve de production.

## Transactions et migrations

Une opération métier doit conserver la cohérence entre fichier physique et ligne SQL. Les migrations versionnent l’évolution, mais un volume persistant Docker peut conserver un schéma ancien; le runner doit donc s’exécuter et échouer explicitement. La sauvegarde, la rétention et la purge ne sont pas établies par les modèles et demeurent des décisions d’exploitation.

**Lecture d’ingénierie.** Exactitude, confiance, coût et preuve sont distingués; une configuration n’est pas une preuve de production.

## Conclusion du chapitre

Les résultats et limites sont conservés explicitement.

# Chapitre 6 — Moteur de compression IA

*Introduction du chapitre.* Les affirmations sont rattachées au code, aux tests, aux configurations ou aux artefacts historiques.

## Architecture hybride

Hybrid V3 ne remplace pas les codecs classiques: il les orchestre. Les caractéristiques du fichier alimentent Selector V2; la stratégie top-3 évalue un ensemble borné de candidats puis sérialise le meilleur choix dans XAIC v6. Le sélecteur est gelé dans checkpoints/selector_v2/best.json; aucun artefact Selector V3 n’est revendiqué.

**Lecture d’ingénierie.** Exactitude, confiance, coût et preuve sont distingués; une configuration n’est pas une preuve de production.

## CausalByteGRU

Le CausalByteGRU transforme les octets en embeddings, propage un état récurrent et produit des logits sur 256 symboles. Les probabilités doivent être déterministes pour que le décodeur reproduise la même distribution. La porte de mise à jour s’écrit z_t = sigmoid(W_z x_t + U_z h_{t-1}). La porte de réinitialisation s’écrit r_t = sigmoid(W_r x_t + U_r h_{t-1}). L’état candidat combine x_t et le produit élément par élément r_t fois h_{t-1}; l’état final interpole l’ancien état et le candidat selon z_t.

**Lecture d’ingénierie.** Exactitude, confiance, coût et preuve sont distingués; une configuration n’est pas une preuve de production.

## Format, intégrité et compatibilité

Le conteneur enregistre version, stratégie, métadonnées nécessaires et checksums. La compatibilité couvre XAIC v1 à v6 dans les tests historiques du rapport V3. La condition essentielle n’est pas seulement l’ouverture du fichier mais l’égalité SHA-256 entre origine et reconstruction. Un checkpoint absent ou incompatible doit être une erreur explicite, jamais une reconstruction approximative.

**Lecture d’ingénierie.** Exactitude, confiance, coût et preuve sont distingués; une configuration n’est pas une preuve de production.

## Mesures

Le taux CR=taille_originale/taille_compressée; l’économie vaut (1-taille_compressée/taille_originale)×100; BPB=8×taille_compressée/taille_originale. Le débit divise les octets par le temps complet. Le protocole V3 inclut sélection, compression, sérialisation, checksums et round-trip, ce qui évite de présenter une micro-mesure de codec comme temps utilisateur.

**Lecture d’ingénierie.** Exactitude, confiance, coût et preuve sont distingués; une configuration n’est pas une preuve de production.

## Conclusion du chapitre

Les résultats et limites sont conservés explicitement.

# Chapitre 7 — Méthodologie d’entraînement

*Introduction du chapitre.* Les affirmations sont rattachées au code, aux tests, aux configurations ou aux artefacts historiques.

## Corpus et fenêtrage

Les scripts construisent des corpus par familles, excluent les artefacts impropres, bornent les octets par fichier et produisent des fenêtres causales. Plusieurs configurations existent: contextes 64, 128, 256 et recherche 512; le checkpoint Kaggle documente contexte 256, stride 128, maximum 32 MiB par fichier et seed 42. Ces valeurs sont attachées aux artefacts concernés et non généralisées à tous les modèles.

**Lecture d’ingénierie.** Exactitude, confiance, coût et preuve sont distingués; une configuration n’est pas une preuve de production.

## Optimisation

La tâche minimise la cross-entropie du prochain octet. Les historiques montrent notamment un apprentissage à 0,001 puis décroissance pour le checkpoint Kaggle, et 0,0001 dans l’historique neural_lossless_v2. DataLoader, batch, découpage et échantillonnage doivent conserver l’étanchéité train/validation. Une loss favorable justifie la modélisation, mais seule l’encodeur réel établit les BPB d’artefact.

**Lecture d’ingénierie.** Exactitude, confiance, coût et preuve sont distingués; une configuration n’est pas une preuve de production.

## Sélection et reproductibilité

Le seed, le manifeste de corpus, l’empreinte du checkpoint, la configuration et l’environnement doivent être conservés ensemble. Le Selector V2 atteint top-1 0,666667, top-2 0,810753 et top-3 0,890323 dans son rapport; sa latence d’inférence indiquée est 0,325453 ms. Ces métriques de classement n’impliquent pas que la taille finale bat le meilleur codec fixe.

**Lecture d’ingénierie.** Exactitude, confiance, coût et preuve sont distingués; une configuration n’est pas une preuve de production.

## Conclusion du chapitre

Les résultats et limites sont conservés explicitement.

# Chapitre 8 — Architecture de sécurité

*Introduction du chapitre.* Les affirmations sont rattachées au code, aux tests, aux configurations ou aux artefacts historiques.

## Défense en profondeur

Le mot de passe est haché; les tokens persistants et codes sont hachés; les JWT expirent; TOTP ajoute une preuve temporelle; l’autorisation vérifie propriétaire ou rôle; SHA-256 protège l’intégrité; ClamAV et YARA recherchent respectivement signatures antimalware et motifs; Docker réduit les couplages. Chaque mécanisme couvre une menace différente et aucun ne prouve seul la sûreté globale.

**Lecture d’ingénierie.** Exactitude, confiance, coût et preuve sont distingués; une configuration n’est pas une preuve de production.

## Pipelines fail-closed

Si ClamAV est indisponible, si les règles YARA sont invalides ou si la limite de sortie est dépassée, le traitement est rejeté. Les tests ciblent ces conditions et la non-invocation du moteur après blocage. La décompression applique des bornes avant parsing coûteux, traite en espace temporaire contrôlé et n’expose le résultat qu’après scan.

**Lecture d’ingénierie.** Exactitude, confiance, coût et preuve sont distingués; une configuration n’est pas une preuve de production.

## Menaces et risques résiduels

Les menaces principales sont malware, bombe de décompression, vol de token, bruteforce, rejeu, énumération de compte, client compromis, règles mal configurées et secrets au repos. Les risques résiduels comprennent l’absence de preuve opérationnelle permanente des scanners, la conservation locale de tokens du portail, l’absence de politique de rétention finalisée et la dépendance aux fournisseurs e-mail.

**Lecture d’ingénierie.** Exactitude, confiance, coût et preuve sont distingués; une configuration n’est pas une preuve de production.

## Conclusion du chapitre

Les résultats et limites sont conservés explicitement.

# Chapitre 9 — Authentificateur mobile Flutter

*Introduction du chapitre.* Les affirmations sont rattachées au code, aux tests, aux configurations ou aux artefacts historiques.

## Rôle et états

L’application mobile ne compresse pas: elle guide inscription, vérification d’e-mail, enrôlement TOTP, confirmation serveur, verrouillage local et affichage des codes rotatifs. Le cycle observable comprend démarrage/chargement, non authentifié, vérification, enrôlement, authentifié et verrouillé; les transitions échouent fermées lorsque le stockage ou la biométrie ne sont pas disponibles.

**Lecture d’ingénierie.** Exactitude, confiance, coût et preuve sont distingués; une configuration n’est pas une preuve de production.

## Stockage et biométrie

Le matériel d’authentification est confié au secure storage de la plate-forme. La biométrie protège l’accès local mais ne remplace pas la validation serveur. Un correctif audité refuse désormais le déverrouillage lorsque l’authentification de l’appareil est non supportée. Les OTP, secrets et QR réels doivent être masqués dans toute capture.

**Lecture d’ingénierie.** Exactitude, confiance, coût et preuve sont distingués; une configuration n’est pas une preuve de production.

## Configuration réseau

deployment_config.dart sépare les URL de développement et de production. Sur appareil Android physique, localhost vise le téléphone et non le poste; l’API de développement doit être joignable sur le LAN et déclarée selon la politique réseau Android. En production, HTTPS et une URL fixe vérifiée sont requis.

**Lecture d’ingénierie.** Exactitude, confiance, coût et preuve sont distingués; une configuration n’est pas une preuve de production.

## Conclusion du chapitre

Les résultats et limites sont conservés explicitement.

# Chapitre 10 — Application Desktop Flutter

*Introduction du chapitre.* Les affirmations sont rattachées au code, aux tests, aux configurations ou aux artefacts historiques.

## Architecture

Le desktop propose les modes local et cloud. ApiService gère l’API, LocalEngineService lance le moteur local, HistoryService persiste l’historique, SettingsService conserve la configuration et AppState orchestre session et vues. Cette séparation permet des tests de sérialisation, session et modèles sans exécuter tout le moteur.

**Lecture d’ingénierie.** Exactitude, confiance, coût et preuve sont distingués; une configuration n’est pas une preuve de production.

## Parcours

Les écrans compress, decompress, history, receive et settings couvrent sélection, options, résultats, erreurs, téléchargements et réception de partage. Le chemin cloud dépend du scanner et de l’identité; le chemin local dépend de Python, du package et des checkpoints. Les métriques affichées doivent provenir de mesures persistées, jamais d’une animation de progression.

**Lecture d’ingénierie.** Exactitude, confiance, coût et preuve sont distingués; une configuration n’est pas une preuve de production.

## Limites

L’annulation cloud n’est pas annoncée si aucun endpoint ne la supporte. L’intégrité n’est déclarée vérifiée que si la preuve existe. Les courses d’annulation d’un processus local, les chemins externes et l’installation propre restent à tester sur une distribution signée.

**Lecture d’ingénierie.** Exactitude, confiance, coût et preuve sont distingués; une configuration n’est pas une preuve de production.

## Conclusion du chapitre

Les résultats et limites sont conservés explicitement.

# Chapitre 11 — Portail Angular

*Introduction du chapitre.* Les affirmations sont rattachées au code, aux tests, aux configurations ou aux artefacts historiques.

## Architecture front-end

Les composants couvrent authentification, tableau de bord, compression, décompression, historique, partage, sécurité et paramètres. Les services centralisent API et session; l’intercepteur sérialise le refresh pour éviter plusieurs renouvellements concurrents. Une erreur irrécupérable efface la session expirée.

**Lecture d’ingénierie.** Exactitude, confiance, coût et preuve sont distingués; une configuration n’est pas une preuve de production.

## UX et sécurité

Les routes protégées nécessitent un guard. Le portail n’effectue pas d’autorisation définitive: il masque pour l’ergonomie tandis que l’API décide. Les téléchargements initient une sauvegarde navigateur sans constituer une preuve de persistance disque. Les erreurs de scanner indiquent une indisponibilité de traitement, non un faux succès.

**Lecture d’ingénierie.** Exactitude, confiance, coût et preuve sont distingués; une configuration n’est pas une preuve de production.

## Validation

Vingt-quatre définitions de tests TypeScript ont été recensées, mais l’audit produit signale qu’aucune cible de test Angular active n’était configurée. Il faut donc distinguer l’existence des specs de leur exécution actuelle et conserver la validation navigateur E2E comme exigence avant livraison.

**Lecture d’ingénierie.** Exactitude, confiance, coût et preuve sont distingués; une configuration n’est pas une preuve de production.

## Conclusion du chapitre

Les résultats et limites sont conservés explicitement.

# Chapitre 12 — Site public Next.js

*Introduction du chapitre.* Les affirmations sont rattachées au code, aux tests, aux configurations ou aux artefacts historiques.

## Positionnement

Le site public explique le produit, oriente vers le portail, expose l’état et la distribution. Il ne doit pas simuler des performances, des tarifs ou une disponibilité. Le manifeste de versions détermine les boutons de téléchargement; en l’absence d’artefact signé, les actions restent désactivées.

**Lecture d’ingénierie.** Exactitude, confiance, coût et preuve sont distingués; une configuration n’est pas une preuve de production.

## État et partage public

La page d’état consomme /public/status et ne déduit pas la santé complète d’un simple /health. La page de partage public révèle seulement qu’une authentification est nécessaire; nom, taille et codec restent derrière l’autorisation du destinataire. robots et noindex limitent l’indexation de ces pages sensibles.

**Lecture d’ingénierie.** Exactitude, confiance, coût et preuve sont distingués; une configuration n’est pas une preuve de production.

## Limites de publication

L’audit récent a observé du contenu déployé ancien et des routes manquantes, sans autoriser ce rapport à affirmer qu’elles sont corrigées en production. La documentation publique et les politiques juridiques restent incomplètes; les claims de conformité, zero-knowledge ou chiffrement de bout en bout ne sont pas établis.

**Lecture d’ingénierie.** Exactitude, confiance, coût et preuve sont distingués; une configuration n’est pas une preuve de production.

## Conclusion du chapitre

Les résultats et limites sont conservés explicitement.

# Chapitre 13 — Administration .NET

*Introduction du chapitre.* Les affirmations sont rattachées au code, aux tests, aux configurations ou aux artefacts historiques.

## Architecture Blazor

L’administration Blazor Server conserve les tokens dans le circuit serveur, vérifie /admin/stats après connexion et efface la session sur 401/403. Le tableau de bord lit des données API: utilisateurs, fichiers, audit, état scanner et configuration e-mail assainie.

**Lecture d’ingénierie.** Exactitude, confiance, coût et preuve sont distingués; une configuration n’est pas une preuve de production.

## Fonctions réellement disponibles

Les vues utilisateurs et jobs sont en lecture; l’audit est borné; système et scanner exposent un état. Incidents, quarantaine, suspension, changement de rôle et suppression ne disposent pas de modèles/API complets et sont présentés comme indisponibles. Cette retenue évite une interface d’administration fictive ou dangereuse.

**Lecture d’ingénierie.** Exactitude, confiance, coût et preuve sont distingués; une configuration n’est pas une preuve de production.

## Contrôles

Le rôle admin est vérifié côté API. Le logout tente de révoquer le refresh token mais ne transforme pas instantanément un access token déjà émis en jeton invalide. Pagination, tests .NET dédiés et session navigateur authentifiée constituent des lacunes.

**Lecture d’ingénierie.** Exactitude, confiance, coût et preuve sont distingués; une configuration n’est pas une preuve de production.

## Conclusion du chapitre

Les résultats et limites sont conservés explicitement.

# Chapitre 14 — E-mail et cycle de compte

*Introduction du chapitre.* Les affirmations sont rattachées au code, aux tests, aux configurations ou aux artefacts historiques.

## Providers

Le service distingue SMTP, Mailpit en local, Brevo et Resend selon configuration. Mailpit capture les messages sans livraison externe et facilite les tests. En production, l’expéditeur, le domaine et les secrets appartiennent au fournisseur et doivent être vérifiés hors du dépôt.

**Lecture d’ingénierie.** Exactitude, confiance, coût et preuve sont distingués; une configuration n’est pas une preuve de production.

## Cycle

Inscription, code e-mail, activation, connexion, MFA, session et récupération sont des états reliés, pas des écrans isolés. Les réponses d’oubli de mot de passe doivent rester suffisamment uniformes pour limiter l’énumération. Les codes ont expiration, compteur de tentatives et usage unique; les journaux ne doivent contenir ni code ni jeton.

**Lecture d’ingénierie.** Exactitude, confiance, coût et preuve sont distingués; une configuration n’est pas une preuve de production.

## Pièces jointes et limites

Les capacités e-mail sont exposées par endpoint afin que le client ne suppose pas le support d’une pièce jointe. Le succès HTTP d’un fournisseur ne prouve pas la remise dans la boîte du destinataire; la validation finale requiert réception réelle et analyse des rebonds.

**Lecture d’ingénierie.** Exactitude, confiance, coût et preuve sont distingués; une configuration n’est pas une preuve de production.

## Conclusion du chapitre

Les résultats et limites sont conservés explicitement.

# Chapitre 15 — Conteneurisation et DevOps

*Introduction du chapitre.* Les affirmations sont rattachées au code, aux tests, aux configurations ou aux artefacts historiques.

## Docker Compose

Compose orchestre API, PostgreSQL, ClamAV et Mailpit, avec réseaux, volumes, variables et health checks. Les données PostgreSQL persistantes survivent au conteneur; les migrations restent donc obligatoires. Les images PyTorch peuvent être lourdes et augmentent temps de build et surface de dépendances.

**Lecture d’ingénierie.** Exactitude, confiance, coût et preuve sont distingués; une configuration n’est pas une preuve de production.

## Environnements

Le développement accepte des origines et hôtes locaux explicitement déclarés; la production exige secrets forts, HTTPS, scanners réels et comptes administrateur provisionnés. Les fichiers .env sont des entrées sensibles et le rapport ne lit ni ne reproduit leurs valeurs. Les configurations Vercel/Render constituent des intentions vérifiables, pas une attestation de mise en ligne.

**Lecture d’ingénierie.** Exactitude, confiance, coût et preuve sont distingués; une configuration n’est pas une preuve de production.

## CI/CD et exploitation

La présence de workflows et checklists facilite lint, tests et builds, mais les gates finales incluent signature des applications, migrations, scan réel, round-trip et smoke tests authentifiés. Kubernetes, Vault et monitoring apparaissent comme infrastructure préparatoire; leur présence ne prouve pas un cluster exploité.

**Lecture d’ingénierie.** Exactitude, confiance, coût et preuve sont distingués; une configuration n’est pas une preuve de production.

## Conclusion du chapitre

Les résultats et limites sont conservés explicitement.

# Chapitre 16 — Tests et assurance qualité

*Introduction du chapitre.* Les affirmations sont rattachées au code, aux tests, aux configurations ou aux artefacts historiques.

## Stratégie

La pyramide combine tests unitaires de fonctions pures, intégration SQL/API, contrats croisés, scanners simulés et tests moteur. L’inventaire actuel compte 124 définitions backend, 146 moteur, 36 desktop, 24 Angular et 12 mobile. Ces nombres décrivent le source; les résultats historiques documentent 93 backend, 15 mobile, 5 desktop avec un live test ignoré, et 207 Python plus 3 ignorés pour V3. Ils ne sont pas mélangés.

**Lecture d’ingénierie.** Exactitude, confiance, coût et preuve sont distingués; une configuration n’est pas une preuve de production.

## Sécurité et régression

Les scénarios couvrent scanner absent, règle YARA invalide, origine CORS, limites avant parsing, erreur assainie, upload bloqué sans compression, partage expiré/révoqué, migrations et MFA. Un test mocké valide la logique mais pas le daemon, la DLL, la connectivité ou la fraîcheur des signatures en production.

**Lecture d’ingénierie.** Exactitude, confiance, coût et preuve sont distingués; une configuration n’est pas une preuve de production.

## Critères de sortie

Une release doit produire builds propres, round-trip SHA, scanners opérationnels, migrations appliquées, e-mail reçu, MFA sur téléphone réel, installation signée et navigation multi-écran. Toute preuve manquante reste BLOCKED plutôt qu’inférée.

**Lecture d’ingénierie.** Exactitude, confiance, coût et preuve sont distingués; une configuration n’est pas une preuve de production.

## Conclusion du chapitre

Les résultats et limites sont conservés explicitement.

# Chapitre 17 — Performances et résultats

*Introduction du chapitre.* Les affirmations sont rattachées au code, aux tests, aux configurations ou aux artefacts historiques.

## Protocole V3

Le benchmark corrigé utilise 140 fichiers held-out uniques, 368 446 658 octets originaux et une comparaison appariée. Les temps incluent sélection, compression, conteneur, checksums et décompression. Trois répétitions sont utilisées jusqu’à 4 MiB, une au-delà; Brotli-11 n’a qu’une répétition car son coût est prohibitif. Les limites doivent accompagner toute généralisation.

**Lecture d’ingénierie.** Exactitude, confiance, coût et preuve sont distingués; une configuration n’est pas une preuve de production.

## Résultats

Hybrid V3 produit 362 188 760 octets, 7,864124 BPB, 18,027349 MiB/s en compression et 32,202720 MiB/s en décompression. Brotli-11 produit 359 459 933 octets, 7,804873 BPB, 0,251334 MiB/s et 194,827433 MiB/s. V3 est 0,7591 % plus grand, mais son débit de compression est environ 70,7 fois celui de Brotli-11 selon le rapport. Les 140 fichiers sont tous perdus en taille face à Brotli-11, ce qui interdit une prétention de meilleur ratio.

**Lecture d’ingénierie.** Exactitude, confiance, coût et preuve sont distingués; une configuration n’est pas une preuve de production.

## Interprétation

V3 améliore V2 de 1,0139 % en taille et de 220,2570 % en vitesse; il est proche de V1 en taille (+0,1318 %) tout en étant nettement plus rapide. La valeur produit dépend donc de la pondération latence/stockage. La décompression Brotli demeure beaucoup plus rapide; le choix top-3 est pertinent pour l’encodage interactif, pas automatiquement pour l’archivage minimal.

**Lecture d’ingénierie.** Exactitude, confiance, coût et preuve sont distingués; une configuration n’est pas une preuve de production.

## Conclusion du chapitre

Les résultats et limites sont conservés explicitement.

# Chapitre 18 — Défis, limites et perspectives

*Introduction du chapitre.* Les affirmations sont rattachées au code, aux tests, aux configurations ou aux artefacts historiques.

## Défis d’ingénierie

Les difficultés étayées incluent configuration API par plate-forme, Android sur LAN, persistance des migrations Docker, alignement audit_events.updated_at, providers e-mail, cycle MFA, fail-closed scanner, performance neuronale et poids PyTorch. Le diagnostic a consisté à isoler frontière, reproduire par test, corriger sans affaiblir le contrôle puis ajouter une régression.

**Lecture d’ingénierie.** Exactitude, confiance, coût et preuve sont distingués; une configuration n’est pas une preuve de production.

## Limites actuelles

La production n’est pas attestée de bout en bout; l’authentificateur n’est pas validé sur téléphone signé; Angular ne possède pas une cible de test active; l’administration n’a pas de projet de tests; la rétention et la suppression de compte ne sont pas implémentées; les secrets TOTP n’ont pas de preuve de chiffrement applicatif au repos; Brotli-11 reste plus compact; l’explicabilité est une traçabilité de sélection, non une explication neuronale fine.

**Lecture d’ingénierie.** Exactitude, confiance, coût et preuve sont distingués; une configuration n’est pas une preuve de production.

## Perspectives

Les travaux futurs prioritaires sont la quantification et le profiling CPU, un sélecteur calibré coût/temps, des explications par caractéristiques, object storage, jobs distribués, observabilité, scans isolés, rotation de clés, stockage matériel mobile, CI/CD signé et dataset versionné. Kubernetes n’est justifié qu’après mesure de charge; la complexité ne doit pas précéder le besoin.

**Lecture d’ingénierie.** Exactitude, confiance, coût et preuve sont distingués; une configuration n’est pas une preuve de production.

## Conclusion générale

XAI-Compress démontre une architecture multi-client intégrant compression adaptative, contrôle de contenu, identité forte et preuves expérimentales. Sa contribution la plus solide est la cohérence entre sélection hybride, conteneur déterministe, SHA-256 et défense en profondeur. Les résultats V3 révèlent un compromis clair: forte accélération de compression par rapport à Brotli-11, au prix d’un léger surcoût de taille. Le projet atteint un niveau de prototype d’ingénierie riche et testable, mais la livraison industrielle reste conditionnée par les validations réelles, la signature, la politique de données et l’exploitation continue des scanners.

**Lecture d’ingénierie.** Exactitude, confiance, coût et preuve sont distingués; une configuration n’est pas une preuve de production.

## Conclusion du chapitre

Les résultats et limites sont conservés explicitement.

# Bibliographie

- RFC 1951 — DEFLATE Compressed Data Format Specification, IETF, 1996.
- RFC 7519 — JSON Web Token (JWT), IETF, 2015.
- RFC 6238 — TOTP: Time-Based One-Time Password Algorithm, IETF, 2011.
- Cho et al., Learning Phrase Representations using RNN Encoder–Decoder, EMNLP, 2014.
- OWASP, Authentication Cheat Sheet et File Upload Cheat Sheet, documentation officielle.
- FastAPI, Security and Dependencies, documentation officielle.
- Flutter, Secure storage and platform integration, documentation officielle.
- Angular, Routing, guards and HTTP interceptors, documentation officielle.
- Next.js, Deployment and security documentation, documentation officielle.
- PostgreSQL, Constraints, transactions and indexes, documentation officielle.
- Docker, Compose specification and secrets, documentation officielle.
- ClamAV, clamd and signature database documentation, documentation officielle.
- VirusTotal, YARA documentation, documentation officielle.
- PyTorch, GRU and reproducibility documentation, documentation officielle.
- Google, Brotli format and implementation documentation.

# Annexes

Les inventaires complets se trouvent dans le DOCX, le fichier de preuves et la checklist de captures.
from pathlib import Path
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from PIL import Image, ImageDraw, ImageFont
import re, shutil, zipfile

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'FINAL_REPORT'; FIG=OUT/'figures'; EVI=OUT/'evidence'
for p in [OUT,FIG/'architecture',FIG/'security',FIG/'ai',FIG/'database',FIG/'deployment',EVI]: p.mkdir(parents=True,exist_ok=True)

NAVY='17365D'; BLUE='2E75B6'; CYAN='DDEBF7'; LIGHT='F3F6F9'; GOLD='C69214'; RED='A61B1B'; GRAY='666666'; WHITE='FFFFFF'

def font(size=11,bold=False,color='000000'):
    try: return ImageFont.truetype('C:/Windows/Fonts/arial.ttf',size)
    except: return ImageFont.load_default()

def diagram(path,title,columns,footer):
    W,H=1800,980; im=Image.new('RGB',(W,H),'white'); d=ImageDraw.Draw(im)
    d.rounded_rectangle((35,35,W-35,H-35),radius=22,outline='#17365D',width=4,fill='#F8FAFC')
    d.text((80,70),title,font=font(38),fill='#17365D')
    y=170; maxrows=max(len(c) for c in columns); colw=(W-160)//len(columns)
    for ci,col in enumerate(columns):
        x=80+ci*colw
        for ri,label in enumerate(col):
            yy=y+ri*145; fill=['#DDEBF7','#E2F0D9','#FFF2CC','#FCE4D6'][ci%4]
            d.rounded_rectangle((x,yy,x+colw-55,yy+88),radius=16,fill=fill,outline='#2E75B6',width=3)
            lines=[]; words=label.split(); line=''
            for w in words:
                if len(line+' '+w)>25: lines.append(line); line=w
                else: line=(line+' '+w).strip()
            lines.append(line)
            for k,l in enumerate(lines[:3]): d.text((x+18,yy+15+k*24),l,font=font(21),fill='#17365D')
            if ri<len(col)-1:
                cx=x+(colw-55)//2; d.line((cx,yy+88,cx,yy+135),fill='#6B7C93',width=4); d.polygon([(cx-8,yy+125),(cx+8,yy+125),(cx,yy+138)],fill='#6B7C93')
    d.text((80,H-80),footer,font=font(20),fill='#555555')
    im.save(path,dpi=(180,180))

diagrams=[
 ('architecture/system_context.png','Contexte du système XAI-Compress',[["Utilisateurs et administrateurs","Clients Web, Desktop, Mobile"],["API REST FastAPI","PostgreSQL et stockage"],["Moteur XAI-Compress","ClamAV + YARA"]],"Frontières: poste client | Internet/TLS | services applicatifs | données"),
 ('architecture/component_architecture.png','Architecture logique multi-client',[["Next.js public","Angular portail","Flutter Desktop"],["Flutter Authenticator","Admin Blazor .NET","FastAPI REST"],["SQLAlchemy / PostgreSQL","Moteur hybride V3","Services e-mail"]],"Les clients partagent un contrat d'API, sans accès direct à la base."),
 ('architecture/data_flow.png','Flux de données principal',[["Sélection du fichier","Upload multipart","Validation bornée"],["Empreinte SHA-256","Analyse ClamAV","Analyse YARA"],["Routage codec","Conteneur XAIC","Historique / téléchargement"]],"Le traitement n'est libéré qu'après les contrôles applicables."),
 ('architecture/deployment.png','Déploiement et orchestration',[["Vercel: Next.js","Vercel: Angular"],["Render: FastAPI","Render: Admin .NET"],["PostgreSQL","ClamAV","Stockage persistant"]],"Topologie déclarée par les configurations; le déploiement effectif reste à valider."),
 ('database/erd.png','Modèle relationnel synthétique',[["users","refresh_tokens","totp_enrollments"],["files","share_codes","audit_events"],["authenticator_devices","auth_challenges","auth_events","recovery_codes"]],"Les clés étrangères relient l'identité, les artefacts et la traçabilité."),
 ('security/upload_pipeline.png','Pipeline sécurisé de téléversement',[["Contrôle taille/type","Écriture temporaire bornée"],["SHA-256","ClamAV","YARA"],["Rejet fermé ou compression","Persistance métadonnées","Audit"]],"Une erreur de scanner produit une indisponibilité, pas une acceptation implicite."),
 ('security/decompression_pipeline.png','Pipeline sécurisé de décompression',[["Validation XAIC","Limites pré-analyse"],["Décompression contrôlée","SHA-256 round-trip"],["ClamAV + YARA","Libération ou rejet"]],"Les limites de ressources précèdent les traitements coûteux."),
 ('security/auth_sequence.png','Séquence d’authentification',[["E-mail + mot de passe","Vérification du hachage"],["Exigence MFA","Validation TOTP"],["JWT d’accès","Refresh token haché","Révocation à la déconnexion"]],"Le jeton court et le renouvellement persistant ont des cycles de vie distincts."),
 ('security/mfa_sequence.png','Enrôlement MFA / TOTP',[["Compte vérifié","Démarrer enrôlement"],["Secret provisionné","Confirmation TOTP"],["Activation","Stockage sécurisé mobile","Codes de récupération"]],"Aucun secret TOTP ni OTP réel n'est inclus dans le rapport."),
 ('ai/compression_pipeline.png','Pipeline Hybrid V3',[["Extraction de caractéristiques","Selector V2 top-3"],["Essais candidats bornés","Choix taille/temps"],["Sérialisation XAIC v6","SHA-256","Décompression déterministe"]],"Production: hybrid_v3_top3; le sélecteur V2 demeure gelé."),
 ('ai/training_pipeline.png','Entraînement byte-level causal',[["Corpus et exclusions","Découpage train/validation"],["Fenêtres de contexte","CausalByteGRU","Cross-entropie"],["Checkpoints","BPB validation","Benchmark artefact réel"]],"La loss de validation ne remplace pas la mesure de taille du conteneur."),
 ('deployment/docker_architecture.png','Architecture Docker Compose',[["Frontends optionnels","API FastAPI"],["PostgreSQL","ClamAV","Mailpit local"],["Volumes","Health checks","Réseau interne"]],"Les secrets sont injectés par variables d'environnement, jamais documentés en valeur."),
]
for rel,t,c,f in diagrams: diagram(FIG/rel,t,c,f)

chapters=[
('Introduction générale',[
('Contexte et problématique',"La croissance des données accentue simultanément les coûts de stockage, le temps de transfert et la surface d’attaque liée au traitement des fichiers. Une plate-forme de compression moderne ne peut donc être évaluée sur le seul taux de réduction: elle doit préserver exactement les octets, borner les ressources, contrôler les contenus hostiles et offrir un parcours cohérent sur plusieurs clients. La problématique retenue est la suivante: comment concevoir une plate-forme multi-client capable de sélectionner une stratégie de compression sans perte selon les caractéristiques d’un fichier, tout en assurant intégrité, authentification forte, analyse antimalware et traçabilité, avec des résultats reproductibles et sans transformer une meilleure vitesse en prétention infondée de meilleure compression?"),
('Objectifs et méthode',"XAI-Compress articule un site public Next.js, un portail Angular, un client Flutter Desktop, un authentificateur Flutter, une administration Blazor .NET et une API FastAPI. L’audit suit une méthode de preuve: lecture du code, rapprochement des configurations, inspection des migrations, analyse des tests et confrontation aux rapports de benchmark. Les faits sont marqués comme vérifiés, historiques, proposés ou manquants. Cette discipline est indispensable lorsque l’architecture déclarée excède ce qui a été validé en production."),
('Organisation du mémoire',"Les chapitres progressent de l’état de l’art et des exigences vers l’architecture, l’implémentation, l’IA, la sécurité et les clients. Ils se terminent par le DevOps, les tests, les résultats, les difficultés et les perspectives. Les annexes consolident les endpoints, variables sans valeurs, tables, preuves et captures à produire.")]),
('Chapitre 1 — Contexte et état de l’art',[
('Fondements de la compression',"La compression sans perte exploite la redondance statistique sans modifier le message reconstruit. Huffman affecte des mots courts aux symboles fréquents; LZ77 et LZ78 décrivent des répétitions par références; LZW construit un dictionnaire; DEFLATE associe LZ77 et Huffman; gzip et ZIP ajoutent des conteneurs et métadonnées; LZMA recherche des ratios élevés au prix d’un calcul plus important. Aucun algorithme ne domine universellement: les médias déjà compressés, les petits fichiers et les données quasi aléatoires déplacent le compromis entre en-tête, ratio, mémoire et latence."),
('Modélisation neuronale et codage entropique',"Un modèle causal byte-level estime p(x_t|x_{<t}) sur 256 valeurs. La cross-entropie moyenne, exprimée en bits par octet, approche le coût idéal d’un code entropique, mais le conteneur réel ajoute modèle, métadonnées, checksums et alignement. La GRU utilise une porte de mise à jour z_t, une porte de réinitialisation r_t et un état h_t; elle réduit le problème de gradient par rapport au RNN simple, avec moins de paramètres qu’une LSTM. La décompression impose exactement le même modèle, le même checkpoint et le même ordre numérique."),
('Positionnement XAI',"Le nom XAI-Compress ne correspond pas, dans le code audité, à une méthode complète d’explicabilité locale de type SHAP appliquée à chaque octet. La dimension explicable réside surtout dans le sélecteur de codecs, les caractéristiques observables, les routes top-3, les rapports d’ablation et la traçabilité des décisions. Cette interprétation limitée est plus fidèle que l’affirmation d’une IA intrinsèquement explicable."),
('Comparaison critique',"Les solutions classiques sont matures, portables et souvent plus compactes. L’approche hybride vise surtout un routage adaptatif et un meilleur compromis de débit. Les mesures V3 montrent précisément cette nuance: Hybrid V3 est beaucoup plus rapide que Brotli-11 sur le corpus retenu, mais produit un artefact légèrement plus grand. La contribution scientifique tient donc à la sélection contrôlée, au protocole de comparaison et à l’intégration sécurisée, non à une victoire universelle sur Brotli.")]),
('Chapitre 2 — Analyse et spécification des besoins',[
('Acteurs et responsabilités',"L’utilisateur standard crée un compte, vérifie son adresse, active éventuellement le MFA, compresse, décompresse, télécharge, consulte l’historique et partage. L’administrateur observe utilisateurs, fichiers, scanner et événements sans qu’une interface visible ne remplace l’autorisation serveur. L’authentificateur mobile provisionne et protège le facteur TOTP. Les services externes comprennent la messagerie, PostgreSQL et les scanners."),
('Exigences fonctionnelles',"Les préconditions critiques sont l’identité validée, l’autorisation sur la ressource, la taille admissible et la disponibilité des scanners. Chaque opération produit un résultat vérifiable ou une erreur non ambiguë. Un partage est lié à un destinataire, une expiration, un nombre de téléchargements et une révocation. La décompression ne doit jamais publier un contenu avant validation du conteneur et contrôle antimalware."),
('Exigences non fonctionnelles',"La confidentialité des secrets, l’intégrité SHA-256, le fail-closed, les limites de ressources, l’audit, la maintenabilité par composants, la portabilité des clients et la reproductibilité des benchmarks forment les exigences structurantes. La disponibilité n’autorise pas l’abaissement silencieux des contrôles. La scalabilité est aujourd’hui limitée par le traitement local et le stockage configuré; l’objet storage et la file distribuée restent des perspectives.")]),
('Chapitre 3 — Architecture globale',[
('Architecture logique',"Tous les clients communiquent avec FastAPI par REST. L’API concentre validation, identité, autorisation et orchestration; SQLAlchemy isole la persistance; le moteur est invoqué derrière une frontière de service; les scanners forment une barrière avant et après transformation. Ce découplage évite que les clients manipulent des chemins serveur ou des secrets de base de données."),
('Flux et frontières de confiance',"Le poste client, Internet, la terminaison TLS, l’API, le réseau Docker, la base et le stockage sont des zones distinctes. Un nom de fichier et un MIME sont non fiables; l’identité portée par un JWT est vérifiée mais l’autorisation doit encore contrôler le propriétaire. Les sorties du moteur ne deviennent pas sûres par leur seule provenance: elles sont bornées, vérifiées et rescannées."),
('Architecture physique et déploiement',"Les configurations prévoient Vercel pour les frontends et Render pour les services applicatifs, tandis que Compose assemble le développement avec PostgreSQL, ClamAV et Mailpit. Ce rapport distingue la topologie définie du déploiement effectivement prouvé: aucune disponibilité de production n’est déduite d’un fichier de configuration.")]),
('Chapitre 4 — Backend FastAPI',[
('Organisation et contrats REST',"Les modules main.py, account.py, mfa.py et authenticator.py enregistrent 43 routes observées. Pydantic valide les entrées; les dépendances FastAPI extraient l’utilisateur; SQLAlchemy gère les unités de travail. Les réponses publiques d’état sont volontairement assainies. CORS dépend d’une liste d’origines et les tests couvrent le rejet d’une origine non autorisée."),
('Cycle d’identité',"L’inscription hache le mot de passe et crée un compte non vérifié. La vérification e-mail utilise un code haché, borné en tentatives et en expiration. La connexion vérifie les identifiants puis le MFA selon la politique. Le JWT d’accès est court; le refresh token n’est persisté que sous forme de hachage et peut être révoqué. L’oubli de mot de passe sépare demande, vérification de code et remplacement, ce qui réduit la durée d’exposition d’un jeton de réinitialisation."),
('Traitement de fichiers et erreurs',"Le téléversement est copié sous limites, haché, scanné puis transmis au moteur. Les erreurs internes sont traduites sans exposer chemins ni commandes. L’historique est filtré par propriétaire; l’administration utilise un contrôle de rôle. Les migrations 003/004 et leur runner sont testés, notamment pour maintenir l’alignement de audit_events et de son updated_at.")]),
('Chapitre 5 — Base de données',[
('Modèle conceptuel',"Le noyau lie users aux fichiers, tokens, défis, dispositifs et événements. files conserve tailles, codec, empreinte, chemins internes, statut et preuve d’intégrité. share_codes relie fichier, émetteur et destinataire sans stocker le code en clair. audit_events et auth_events séparent l’audit fonctionnel de la chronologie d’authentification."),
('Contraintes et données sensibles',"Les e-mails, identifiants de dispositif et hachages de tokens sont indexés ou uniques selon leur rôle. Les secrets TOTP sont sensibles et ne doivent jamais apparaître dans les logs; le code actuel nécessite leur disponibilité serveur pour valider le facteur, sans preuve d’un chiffrement applicatif au repos. Les chemins d’artefacts sont internes et ne constituent pas des URL publiques."),
('Transactions et migrations',"Une opération métier doit conserver la cohérence entre fichier physique et ligne SQL. Les migrations versionnent l’évolution, mais un volume persistant Docker peut conserver un schéma ancien; le runner doit donc s’exécuter et échouer explicitement. La sauvegarde, la rétention et la purge ne sont pas établies par les modèles et demeurent des décisions d’exploitation.")]),
('Chapitre 6 — Moteur de compression IA',[
('Architecture hybride',"Hybrid V3 ne remplace pas les codecs classiques: il les orchestre. Les caractéristiques du fichier alimentent Selector V2; la stratégie top-3 évalue un ensemble borné de candidats puis sérialise le meilleur choix dans XAIC v6. Le sélecteur est gelé dans checkpoints/selector_v2/best.json; aucun artefact Selector V3 n’est revendiqué."),
('CausalByteGRU',"Le CausalByteGRU transforme les octets en embeddings, propage un état récurrent et produit des logits sur 256 symboles. Les probabilités doivent être déterministes pour que le décodeur reproduise la même distribution. La porte de mise à jour s’écrit z_t = sigmoid(W_z x_t + U_z h_{t-1}). La porte de réinitialisation s’écrit r_t = sigmoid(W_r x_t + U_r h_{t-1}). L’état candidat combine x_t et le produit élément par élément r_t fois h_{t-1}; l’état final interpole l’ancien état et le candidat selon z_t."),
('Format, intégrité et compatibilité',"Le conteneur enregistre version, stratégie, métadonnées nécessaires et checksums. La compatibilité couvre XAIC v1 à v6 dans les tests historiques du rapport V3. La condition essentielle n’est pas seulement l’ouverture du fichier mais l’égalité SHA-256 entre origine et reconstruction. Un checkpoint absent ou incompatible doit être une erreur explicite, jamais une reconstruction approximative."),
('Mesures',"Le taux CR=taille_originale/taille_compressée; l’économie vaut (1-taille_compressée/taille_originale)×100; BPB=8×taille_compressée/taille_originale. Le débit divise les octets par le temps complet. Le protocole V3 inclut sélection, compression, sérialisation, checksums et round-trip, ce qui évite de présenter une micro-mesure de codec comme temps utilisateur.")]),
('Chapitre 7 — Méthodologie d’entraînement',[
('Corpus et fenêtrage',"Les scripts construisent des corpus par familles, excluent les artefacts impropres, bornent les octets par fichier et produisent des fenêtres causales. Plusieurs configurations existent: contextes 64, 128, 256 et recherche 512; le checkpoint Kaggle documente contexte 256, stride 128, maximum 32 MiB par fichier et seed 42. Ces valeurs sont attachées aux artefacts concernés et non généralisées à tous les modèles."),
('Optimisation',"La tâche minimise la cross-entropie du prochain octet. Les historiques montrent notamment un apprentissage à 0,001 puis décroissance pour le checkpoint Kaggle, et 0,0001 dans l’historique neural_lossless_v2. DataLoader, batch, découpage et échantillonnage doivent conserver l’étanchéité train/validation. Une loss favorable justifie la modélisation, mais seule l’encodeur réel établit les BPB d’artefact."),
('Sélection et reproductibilité',"Le seed, le manifeste de corpus, l’empreinte du checkpoint, la configuration et l’environnement doivent être conservés ensemble. Le Selector V2 atteint top-1 0,666667, top-2 0,810753 et top-3 0,890323 dans son rapport; sa latence d’inférence indiquée est 0,325453 ms. Ces métriques de classement n’impliquent pas que la taille finale bat le meilleur codec fixe.")]),
('Chapitre 8 — Architecture de sécurité',[
('Défense en profondeur',"Le mot de passe est haché; les tokens persistants et codes sont hachés; les JWT expirent; TOTP ajoute une preuve temporelle; l’autorisation vérifie propriétaire ou rôle; SHA-256 protège l’intégrité; ClamAV et YARA recherchent respectivement signatures antimalware et motifs; Docker réduit les couplages. Chaque mécanisme couvre une menace différente et aucun ne prouve seul la sûreté globale."),
('Pipelines fail-closed',"Si ClamAV est indisponible, si les règles YARA sont invalides ou si la limite de sortie est dépassée, le traitement est rejeté. Les tests ciblent ces conditions et la non-invocation du moteur après blocage. La décompression applique des bornes avant parsing coûteux, traite en espace temporaire contrôlé et n’expose le résultat qu’après scan."),
('Menaces et risques résiduels',"Les menaces principales sont malware, bombe de décompression, vol de token, bruteforce, rejeu, énumération de compte, client compromis, règles mal configurées et secrets au repos. Les risques résiduels comprennent l’absence de preuve opérationnelle permanente des scanners, la conservation locale de tokens du portail, l’absence de politique de rétention finalisée et la dépendance aux fournisseurs e-mail.")]),
('Chapitre 9 — Authentificateur mobile Flutter',[
('Rôle et états',"L’application mobile ne compresse pas: elle guide inscription, vérification d’e-mail, enrôlement TOTP, confirmation serveur, verrouillage local et affichage des codes rotatifs. Le cycle observable comprend démarrage/chargement, non authentifié, vérification, enrôlement, authentifié et verrouillé; les transitions échouent fermées lorsque le stockage ou la biométrie ne sont pas disponibles."),
('Stockage et biométrie',"Le matériel d’authentification est confié au secure storage de la plate-forme. La biométrie protège l’accès local mais ne remplace pas la validation serveur. Un correctif audité refuse désormais le déverrouillage lorsque l’authentification de l’appareil est non supportée. Les OTP, secrets et QR réels doivent être masqués dans toute capture."),
('Configuration réseau',"deployment_config.dart sépare les URL de développement et de production. Sur appareil Android physique, localhost vise le téléphone et non le poste; l’API de développement doit être joignable sur le LAN et déclarée selon la politique réseau Android. En production, HTTPS et une URL fixe vérifiée sont requis.")]),
('Chapitre 10 — Application Desktop Flutter',[
('Architecture',"Le desktop propose les modes local et cloud. ApiService gère l’API, LocalEngineService lance le moteur local, HistoryService persiste l’historique, SettingsService conserve la configuration et AppState orchestre session et vues. Cette séparation permet des tests de sérialisation, session et modèles sans exécuter tout le moteur."),
('Parcours',"Les écrans compress, decompress, history, receive et settings couvrent sélection, options, résultats, erreurs, téléchargements et réception de partage. Le chemin cloud dépend du scanner et de l’identité; le chemin local dépend de Python, du package et des checkpoints. Les métriques affichées doivent provenir de mesures persistées, jamais d’une animation de progression."),
('Limites',"L’annulation cloud n’est pas annoncée si aucun endpoint ne la supporte. L’intégrité n’est déclarée vérifiée que si la preuve existe. Les courses d’annulation d’un processus local, les chemins externes et l’installation propre restent à tester sur une distribution signée.")]),
('Chapitre 11 — Portail Angular',[
('Architecture front-end',"Les composants couvrent authentification, tableau de bord, compression, décompression, historique, partage, sécurité et paramètres. Les services centralisent API et session; l’intercepteur sérialise le refresh pour éviter plusieurs renouvellements concurrents. Une erreur irrécupérable efface la session expirée."),
('UX et sécurité',"Les routes protégées nécessitent un guard. Le portail n’effectue pas d’autorisation définitive: il masque pour l’ergonomie tandis que l’API décide. Les téléchargements initient une sauvegarde navigateur sans constituer une preuve de persistance disque. Les erreurs de scanner indiquent une indisponibilité de traitement, non un faux succès."),
('Validation',"Vingt-quatre définitions de tests TypeScript ont été recensées, mais l’audit produit signale qu’aucune cible de test Angular active n’était configurée. Il faut donc distinguer l’existence des specs de leur exécution actuelle et conserver la validation navigateur E2E comme exigence avant livraison.")]),
('Chapitre 12 — Site public Next.js',[
('Positionnement',"Le site public explique le produit, oriente vers le portail, expose l’état et la distribution. Il ne doit pas simuler des performances, des tarifs ou une disponibilité. Le manifeste de versions détermine les boutons de téléchargement; en l’absence d’artefact signé, les actions restent désactivées."),
('État et partage public',"La page d’état consomme /public/status et ne déduit pas la santé complète d’un simple /health. La page de partage public révèle seulement qu’une authentification est nécessaire; nom, taille et codec restent derrière l’autorisation du destinataire. robots et noindex limitent l’indexation de ces pages sensibles."),
('Limites de publication',"L’audit récent a observé du contenu déployé ancien et des routes manquantes, sans autoriser ce rapport à affirmer qu’elles sont corrigées en production. La documentation publique et les politiques juridiques restent incomplètes; les claims de conformité, zero-knowledge ou chiffrement de bout en bout ne sont pas établis.")]),
('Chapitre 13 — Administration .NET',[
('Architecture Blazor',"L’administration Blazor Server conserve les tokens dans le circuit serveur, vérifie /admin/stats après connexion et efface la session sur 401/403. Le tableau de bord lit des données API: utilisateurs, fichiers, audit, état scanner et configuration e-mail assainie."),
('Fonctions réellement disponibles',"Les vues utilisateurs et jobs sont en lecture; l’audit est borné; système et scanner exposent un état. Incidents, quarantaine, suspension, changement de rôle et suppression ne disposent pas de modèles/API complets et sont présentés comme indisponibles. Cette retenue évite une interface d’administration fictive ou dangereuse."),
('Contrôles',"Le rôle admin est vérifié côté API. Le logout tente de révoquer le refresh token mais ne transforme pas instantanément un access token déjà émis en jeton invalide. Pagination, tests .NET dédiés et session navigateur authentifiée constituent des lacunes.")]),
('Chapitre 14 — E-mail et cycle de compte',[
('Providers',"Le service distingue SMTP, Mailpit en local, Brevo et Resend selon configuration. Mailpit capture les messages sans livraison externe et facilite les tests. En production, l’expéditeur, le domaine et les secrets appartiennent au fournisseur et doivent être vérifiés hors du dépôt."),
('Cycle',"Inscription, code e-mail, activation, connexion, MFA, session et récupération sont des états reliés, pas des écrans isolés. Les réponses d’oubli de mot de passe doivent rester suffisamment uniformes pour limiter l’énumération. Les codes ont expiration, compteur de tentatives et usage unique; les journaux ne doivent contenir ni code ni jeton."),
('Pièces jointes et limites',"Les capacités e-mail sont exposées par endpoint afin que le client ne suppose pas le support d’une pièce jointe. Le succès HTTP d’un fournisseur ne prouve pas la remise dans la boîte du destinataire; la validation finale requiert réception réelle et analyse des rebonds.")]),
('Chapitre 15 — Conteneurisation et DevOps',[
('Docker Compose',"Compose orchestre API, PostgreSQL, ClamAV et Mailpit, avec réseaux, volumes, variables et health checks. Les données PostgreSQL persistantes survivent au conteneur; les migrations restent donc obligatoires. Les images PyTorch peuvent être lourdes et augmentent temps de build et surface de dépendances."),
('Environnements',"Le développement accepte des origines et hôtes locaux explicitement déclarés; la production exige secrets forts, HTTPS, scanners réels et comptes administrateur provisionnés. Les fichiers .env sont des entrées sensibles et le rapport ne lit ni ne reproduit leurs valeurs. Les configurations Vercel/Render constituent des intentions vérifiables, pas une attestation de mise en ligne."),
('CI/CD et exploitation',"La présence de workflows et checklists facilite lint, tests et builds, mais les gates finales incluent signature des applications, migrations, scan réel, round-trip et smoke tests authentifiés. Kubernetes, Vault et monitoring apparaissent comme infrastructure préparatoire; leur présence ne prouve pas un cluster exploité.")]),
('Chapitre 16 — Tests et assurance qualité',[
('Stratégie',"La pyramide combine tests unitaires de fonctions pures, intégration SQL/API, contrats croisés, scanners simulés et tests moteur. L’inventaire actuel compte 124 définitions backend, 146 moteur, 36 desktop, 24 Angular et 12 mobile. Ces nombres décrivent le source; les résultats historiques documentent 93 backend, 15 mobile, 5 desktop avec un live test ignoré, et 207 Python plus 3 ignorés pour V3. Ils ne sont pas mélangés."),
('Sécurité et régression',"Les scénarios couvrent scanner absent, règle YARA invalide, origine CORS, limites avant parsing, erreur assainie, upload bloqué sans compression, partage expiré/révoqué, migrations et MFA. Un test mocké valide la logique mais pas le daemon, la DLL, la connectivité ou la fraîcheur des signatures en production."),
('Critères de sortie',"Une release doit produire builds propres, round-trip SHA, scanners opérationnels, migrations appliquées, e-mail reçu, MFA sur téléphone réel, installation signée et navigation multi-écran. Toute preuve manquante reste BLOCKED plutôt qu’inférée.")]),
('Chapitre 17 — Performances et résultats',[
('Protocole V3',"Le benchmark corrigé utilise 140 fichiers held-out uniques, 368 446 658 octets originaux et une comparaison appariée. Les temps incluent sélection, compression, conteneur, checksums et décompression. Trois répétitions sont utilisées jusqu’à 4 MiB, une au-delà; Brotli-11 n’a qu’une répétition car son coût est prohibitif. Les limites doivent accompagner toute généralisation."),
('Résultats',"Hybrid V3 produit 362 188 760 octets, 7,864124 BPB, 18,027349 MiB/s en compression et 32,202720 MiB/s en décompression. Brotli-11 produit 359 459 933 octets, 7,804873 BPB, 0,251334 MiB/s et 194,827433 MiB/s. V3 est 0,7591 % plus grand, mais son débit de compression est environ 70,7 fois celui de Brotli-11 selon le rapport. Les 140 fichiers sont tous perdus en taille face à Brotli-11, ce qui interdit une prétention de meilleur ratio."),
('Interprétation',"V3 améliore V2 de 1,0139 % en taille et de 220,2570 % en vitesse; il est proche de V1 en taille (+0,1318 %) tout en étant nettement plus rapide. La valeur produit dépend donc de la pondération latence/stockage. La décompression Brotli demeure beaucoup plus rapide; le choix top-3 est pertinent pour l’encodage interactif, pas automatiquement pour l’archivage minimal.")]),
('Chapitre 18 — Défis, limites et perspectives',[
('Défis d’ingénierie',"Les difficultés étayées incluent configuration API par plate-forme, Android sur LAN, persistance des migrations Docker, alignement audit_events.updated_at, providers e-mail, cycle MFA, fail-closed scanner, performance neuronale et poids PyTorch. Le diagnostic a consisté à isoler frontière, reproduire par test, corriger sans affaiblir le contrôle puis ajouter une régression."),
('Limites actuelles',"La production n’est pas attestée de bout en bout; l’authentificateur n’est pas validé sur téléphone signé; Angular ne possède pas une cible de test active; l’administration n’a pas de projet de tests; la rétention et la suppression de compte ne sont pas implémentées; les secrets TOTP n’ont pas de preuve de chiffrement applicatif au repos; Brotli-11 reste plus compact; l’explicabilité est une traçabilité de sélection, non une explication neuronale fine."),
('Perspectives',"Les travaux futurs prioritaires sont la quantification et le profiling CPU, un sélecteur calibré coût/temps, des explications par caractéristiques, object storage, jobs distribués, observabilité, scans isolés, rotation de clés, stockage matériel mobile, CI/CD signé et dataset versionné. Kubernetes n’est justifié qu’après mesure de charge; la complexité ne doit pas précéder le besoin."),
('Conclusion générale',"XAI-Compress démontre une architecture multi-client intégrant compression adaptative, contrôle de contenu, identité forte et preuves expérimentales. Sa contribution la plus solide est la cohérence entre sélection hybride, conteneur déterministe, SHA-256 et défense en profondeur. Les résultats V3 révèlent un compromis clair: forte accélération de compression par rapport à Brotli-11, au prix d’un léger surcoût de taille. Le projet atteint un niveau de prototype d’ingénierie riche et testable, mais la livraison industrielle reste conditionnée par les validations réelles, la signature, la politique de données et l’exploitation continue des scanners.")])
]

tables={
'Exigences fonctionnelles':[['ID','Exigence','Acteur','Priorité','Résultat attendu'],['F-01','Créer et vérifier un compte','Utilisateur','Haute','Compte activé sans divulgation de code'],['F-02','S’authentifier avec MFA','Utilisateur','Haute','Session et tokens bornés'],['F-03','Compresser un fichier scanné','Utilisateur','Critique','XAIC + SHA + historique'],['F-04','Décompresser sous limites','Utilisateur','Critique','Octets identiques ou rejet'],['F-05','Partager à un destinataire','Utilisateur','Haute','Code haché, expiration, quota'],['F-06','Observer les événements','Admin','Haute','Vue autorisée et assainie']],
'Exigences non fonctionnelles':[['ID','Catégorie','Critère'],['NF-01','Sécurité','Échec fermé si scanner indisponible'],['NF-02','Intégrité','SHA-256 de round-trip'],['NF-03','Performance','Temps bout-en-bout mesuré'],['NF-04','Maintenabilité','Clients découplés du moteur'],['NF-05','Vie privée','Aucun secret dans logs/rapport'],['NF-06','Portabilité','Web, Windows et Android configurables']],
'Résultats Hybrid V3':[['Méthode','Octets compressés','BPB','Comp. MiB/s','Décomp. MiB/s'],['Hybrid V1','361 712 014','7,853772','2,816161','20,174976'],['Hybrid V2 gelé','365 898 448','7,944671','5,629025','30,124013'],['Hybrid V3 top-3','362 188 760','7,864124','18,027349','32,202720'],['Brotli-11','359 459 933','7,804873','0,251334','194,827433']],
'Inventaire des tests':[['Composant','Définitions recensées','Dernière preuve d’exécution distincte'],['FastAPI','124','93 réussis (audit produit)'],['Moteur Python','146','207 réussis, 3 ignorés (rapport V3)'],['Rust','2 cas historiques','2 réussis (rapport V3)'],['Flutter Desktop','36','5 réussis, 1 live ignoré'],['Flutter Mobile','12','15 réussis (audit produit)'],['Angular','24','Specs présentes; cible active non établie']],
'Menaces':[['Menace','Vecteur','Impact','Contrôle','Risque résiduel'],['Malware','Upload','Élevé','ClamAV + YARA','Signatures/daemon'],['Bombe','XAIC forgé','Élevé','Bornes pré-parsing','Codec nouveau'],['Vol token','Client compromis','Élevé','Expiration + révocation refresh','Access token vivant'],['Bruteforce','Login/TOTP','Élevé','Compteurs + expiration','Distribution attaque'],['Rejeu','Code ou défi','Moyen','Nonce/usage unique','Horloge/implémentation'],['Règle invalide','Mauvaise config','Élevé','Fail-closed','Indisponibilité']],
'Dictionnaire de données':[['Table','Finalité','Relations'],['users','Identité, rôle, MFA','Parent de fichiers, tokens et dispositifs'],['totp_enrollments','Enrôlement borné','user_id'],['files','Artefacts et métriques','owner_id'],['share_codes','Partage destinataire','file_id, sender_id'],['audit_events','Traçabilité métier','user_id logique'],['account_verification_challenges','Vérification/récupération','user_id'],['refresh_tokens','Renouvellement révoquable','user_id'],['authenticator_devices','Dispositifs enregistrés','user_id'],['auth_challenges','Défis push/number match','user_id, device_id'],['auth_events','Historique authentification','user_id, device_id'],['recovery_codes','Récupération MFA','user_id'],['auth_policies','Politique globale','scope unique']],
'API principale':[['Méthode','Endpoint','Auth.','But'],['POST','/auth/register','Non','Créer un compte'],['POST','/auth/login','Non/MFA','Ouvrir une session'],['POST','/auth/refresh','Refresh','Renouveler'],['POST','/compression/jobs','JWT','Compresser'],['POST','/compression/decompress','JWT','Décompresser'],['GET','/history','JWT','Historique propriétaire'],['POST','/shares','JWT','Créer partage'],['POST','/shares/redeem','JWT','Racheter partage'],['GET','/admin/audit','Admin','Audit'],['GET','/public/status','Public','État assaini']],
'Technologies':[['Couche','Technologie','Rôle','Limite'],['Public','Next.js','Présentation/statut','Pas de logique d’autorisation'],['Portail','Angular','Parcours fichiers','Tokens côté navigateur'],['Desktop','Flutter','Local et cloud','Dépendances moteur local'],['Authenticator','Flutter','TOTP/biométrie','Validation appareil requise'],['Admin','Blazor .NET','Lecture opérationnelle','Peu de tests dédiés'],['API','FastAPI','Contrats/orchestration','Traitement synchrone'],['Données','PostgreSQL','Persistance','Rétention non finalisée'],['Sécurité','ClamAV/YARA','Analyse','Disponibilité/signatures']],
}

screens=[
('MOBILE-01','Mobile','Création de compte','Ouvrir Inscription','Champs non remplis et bouton','E-mail, mots de passe','Création de compte','9','MANDATORY'),('MOBILE-02','Mobile','Vérification e-mail','Soumettre inscription','Écran code et renvoi','Code et adresse réelle','Vérification de l’adresse','9','MANDATORY'),('MOBILE-03','Mobile','Enrôlement TOTP','Après vérification','Instructions et statut','QR, secret, OTP','Enrôlement authentificateur','9','MANDATORY'),('MOBILE-04','Mobile','Code circulaire','Déverrouiller','Compte fictif et anneau','OTP, e-mail','Code TOTP rotatif','9','RECOMMENDED'),('DESKTOP-01','Desktop','Compression cloud','Connexion puis Compression','Fichier test, mode, statut','Chemin personnel, token','Compression depuis Desktop','10','MANDATORY'),('DESKTOP-02','Desktop','Résultat','Terminer compression','Tailles, codec, SHA masqué','Chemins, empreinte complète','Résultat de compression','10','MANDATORY'),('ANGULAR-01','Angular','Tableau de bord','Connexion portail','Indicateurs et navigation','E-mail personnel','Tableau de bord utilisateur','11','MANDATORY'),('ANGULAR-02','Angular','Compression','Route /compress','Sélecteur, mode, action','Token, fichier privé','Lancement de compression','11','MANDATORY'),('ANGULAR-03','Angular','Historique','Route /history','Table et actions','Noms privés','Historique des opérations','11','RECOMMENDED'),('ADMIN-01','Admin','Dashboard','Connexion admin test','Mesures et état','Comptes réels','Tableau de bord administratif','13','MANDATORY'),('ADMIN-02','Admin','Audit','Ouvrir Audit','Actions assainies','Détails sensibles','Journal d’audit','13','RECOMMENDED'),('PUBLIC-01','Next.js','Accueil','Ouvrir racine','Architecture et CTA','Données démo obsolètes','Site public','12','RECOMMENDED'),('TEST-01','Terminal','Tests backend','Exécuter pytest ciblé','Résumé succès','Chemins/variables','Suite backend','16','MANDATORY'),('TEST-02','Terminal','Tests moteur','Exécuter pytest moteur','Résumé et skips','Chemins personnels','Suite moteur','16','MANDATORY'),('TEST-03','Docker','Services sains','docker compose ps','Health states','Secrets/env','Services Docker','15','MANDATORY'),('SEC-01','Terminal','Validation scanner','Diagnostic contrôlé','ClamAV/YARA ready','Règles privées','Validation scanners','8','MANDATORY'),('DEPLOY-01','Vercel/Render','Déploiements','Ouvrir dashboards','Services et dates','IDs/tokens/logs','Déploiements déclarés','15','RECOMMENDED')]

evidence=[
('43 routes REST observées','services/api_fastapi/app/main.py; account.py; mfa.py; authenticator.py','VERIFIED FROM SOURCE'),('12 tables SQLAlchemy','services/api_fastapi/app/models.py','VERIFIED FROM SOURCE'),('Fail-closed ClamAV/YARA','app/security_scanner.py; tests/test_security_scanner.py; test_product_truth.py','VERIFIED FROM SOURCE/TEST'),('Refresh tokens hachés et révocables','models.py; security.py; main.py','VERIFIED FROM SOURCE'),('MFA TOTP et enrôlement','mfa.py; authenticator.py; mobile lib/core/app_state.dart','VERIFIED FROM SOURCE'),('Hybrid V3 top-3 retenu','engines/XAI-Compress/results/hybrid_v3/final_report.md','HISTORICAL AUTHORITATIVE ARTIFACT'),('140 fichiers, 368446658 octets','engines/XAI-Compress/results/hybrid_v3/final_report.md','HISTORICAL AUTHORITATIVE ARTIFACT'),('Brotli-11 plus compact que V3','engines/XAI-Compress/results/hybrid_v3/final_report.md','HISTORICAL AUTHORITATIVE ARTIFACT'),('Vercel + Render configurés','deployment/README.md; app configs','VERIFIED FROM CONFIG; LIVE NOT PROVEN'),('Mobile secure storage/biométrie','mobile services/secure_account_store.dart; biometric_service.dart','VERIFIED FROM SOURCE'),('Angular refresh sérialisé','apps/web_angular source and product truth audit','VERIFIED FROM SOURCE'),('Admin lecture utilisateurs/jobs/audit','apps/admin_dotnet; API admin routes','VERIFIED FROM SOURCE'),('Production prête','Aucune preuve E2E complète','NOT VERIFIED / DO NOT CLAIM')]

def shade(cell,fill):
    tcPr=cell._tc.get_or_add_tcPr(); shd=OxmlElement('w:shd'); shd.set(qn('w:fill'),fill); tcPr.append(shd)
def margins(cell,top=80,start=100,bottom=80,end=100):
    tc=cell._tc.get_or_add_tcPr(); m=tc.first_child_found_in('w:tcMar')
    if m is None: m=OxmlElement('w:tcMar'); tc.append(m)
    for side,val in [('top',top),('start',start),('bottom',bottom),('end',end)]:
        n=OxmlElement('w:'+side); n.set(qn('w:w'),str(val)); n.set(qn('w:type'),'dxa'); m.append(n)
def add_table(doc,title,rows):
    p=doc.add_paragraph(); p.style='Caption'; p.add_run(title).bold=True
    t=doc.add_table(rows=len(rows),cols=len(rows[0])); t.alignment=WD_TABLE_ALIGNMENT.CENTER; t.autofit=True; t.style='Table Grid'
    for i,row in enumerate(rows):
        for j,v in enumerate(row):
            c=t.cell(i,j); c.text=str(v); margins(c); c.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER
            if i==0:
                shade(c,NAVY)
                for r in c.paragraphs[0].runs:
                    r.font.color.rgb=RGBColor(255,255,255); r.bold=True
            elif i%2==0: shade(c,LIGHT)
            for p2 in c.paragraphs: p2.paragraph_format.space_after=Pt(0); [setattr(r.font,'size',Pt(8.5)) for r in p2.runs]
    doc.add_paragraph('Interprétation — '+('Le tableau met en évidence des contrôles vérifiables et des limites explicitement conservées.' if len(rows)>4 else 'La synthèse soutient la décision technique sans remplacer la preuve source.')).style='Table Note'

def field(run,code):
    b=OxmlElement('w:fldChar'); b.set(qn('w:fldCharType'),'begin'); i=OxmlElement('w:instrText'); i.set(qn('xml:space'),'preserve'); i.text=code; s=OxmlElement('w:fldChar'); s.set(qn('w:fldCharType'),'separate'); e=OxmlElement('w:fldChar'); e.set(qn('w:fldCharType'),'end'); run._r.extend([b,i,s,e])

doc=Document(); sec=doc.sections[0]; sec.page_width=Inches(8.27); sec.page_height=Inches(11.69); sec.top_margin=Inches(.82); sec.bottom_margin=Inches(.78); sec.left_margin=Inches(.9); sec.right_margin=Inches(.75); sec.header_distance=Inches(.35); sec.footer_distance=Inches(.35)
styles=doc.styles; normal=styles['Normal']; normal.font.name='Aptos'; normal.font.size=Pt(10.7); normal.paragraph_format.alignment=WD_ALIGN_PARAGRAPH.JUSTIFY; normal.paragraph_format.space_after=Pt(6); normal.paragraph_format.line_spacing=1.18
for name,size,color,before,after in [('Title',24,NAVY,0,12),('Heading 1',17,NAVY,16,8),('Heading 2',13,BLUE,12,5),('Heading 3',11,GOLD,8,4)]:
    s=styles[name]; s.font.name='Aptos Display'; s.font.size=Pt(size); s.font.color.rgb=RGBColor.from_string(color); s.font.bold=True; s.paragraph_format.space_before=Pt(before); s.paragraph_format.space_after=Pt(after); s.paragraph_format.keep_with_next=True
for name in ['Caption','Table Note']:
    if name not in styles: styles.add_style(name,1)
styles['Caption'].font.name='Aptos'; styles['Caption'].font.size=Pt(9); styles['Caption'].font.bold=True; styles['Caption'].font.color.rgb=RGBColor.from_string(NAVY); styles['Caption'].paragraph_format.keep_with_next=True
styles['Table Note'].font.name='Aptos'; styles['Table Note'].font.size=Pt(8.5); styles['Table Note'].font.italic=True; styles['Table Note'].font.color.rgb=RGBColor.from_string(GRAY)
header=sec.header.paragraphs[0]; header.text='XAI-COMPRESS  |  MÉMOIRE TECHNIQUE'; header.alignment=WD_ALIGN_PARAGRAPH.RIGHT; header.runs[0].font.size=Pt(8); header.runs[0].font.color.rgb=RGBColor.from_string(GRAY)
footer=sec.footer.paragraphs[0]; footer.alignment=WD_ALIGN_PARAGRAPH.CENTER; footer.add_run('XAI-Compress  •  '); field(footer.add_run(),'PAGE')

# cover
for _ in range(4): doc.add_paragraph()
p=doc.add_paragraph('[LOGO UNIVERSITÉ / ÉCOLE]                                  [LOGO ENTREPRISE / LABORATOIRE]'); p.alignment=WD_ALIGN_PARAGRAPH.CENTER
p=doc.add_paragraph('CONCEPTION ET DÉVELOPPEMENT D’UNE PLATEFORME INTELLIGENTE ET SÉCURISÉE DE COMPRESSION DE DONNÉES BASÉE SUR L’INTELLIGENCE ARTIFICIELLE',style='Title'); p.alignment=WD_ALIGN_PARAGRAPH.CENTER
p=doc.add_paragraph('XAI-COMPRESS'); p.alignment=WD_ALIGN_PARAGRAPH.CENTER; p.runs[0].font.size=Pt(28); p.runs[0].font.bold=True; p.runs[0].font.color.rgb=RGBColor.from_string(BLUE)
for line in ['Mémoire de projet de fin d’études','[ÉTABLISSEMENT] — [FORMATION]','Auteur : [À COMPLÉTER]','Encadrant(s) : [À COMPLÉTER]','Année universitaire : [À COMPLÉTER]']: q=doc.add_paragraph(line); q.alignment=WD_ALIGN_PARAGRAPH.CENTER
doc.add_page_break()
for title,text in [('Dédicaces','[À COMPLÉTER — texte personnel facultatif]'),('Remerciements','[À COMPLÉTER — établissement, encadrants, équipe et jury]'),('Résumé',"Ce mémoire présente XAI-Compress, une plate-forme multi-client de compression sans perte qui associe sélection hybride de codecs, API FastAPI, clients Next.js, Angular, Flutter et .NET, persistance PostgreSQL et contrôles ClamAV/YARA. L’étude fondée sur le code et les artefacts expérimentaux montre que Hybrid V3 top-3 améliore fortement le débit de compression face à Brotli-11 sur 140 fichiers, tout en restant 0,7591 % plus volumineux. L’apport majeur est l’intégration vérifiable du routage adaptatif, de l’intégrité SHA-256, du MFA TOTP et du fail-closed. Les limites de production, d’explicabilité fine et de gouvernance sont explicitement distinguées."),('Abstract',"This report presents XAI-Compress, a multi-client lossless-compression platform combining hybrid codec selection, a FastAPI backend, Next.js, Angular, Flutter and .NET clients, PostgreSQL persistence, and ClamAV/YARA controls. Source-grounded evidence shows that Hybrid V3 top-3 greatly improves compression throughput over Brotli-11 on 140 held-out files while producing a 0.7591% larger artifact. The main contribution is the verifiable integration of adaptive routing, SHA-256 integrity, TOTP MFA, and fail-closed processing. Production, fine-grained explainability, and governance limitations are kept explicit.")]:
    doc.add_heading(title,1); doc.add_paragraph(text)
doc.add_paragraph('Mots-clés : compression sans perte, sélection hybride, GRU, FastAPI, Flutter, TOTP, ClamAV, YARA, SHA-256, XAIC.')
doc.add_page_break(); doc.add_heading('Table des matières',1); field(doc.add_paragraph().add_run(),'TOC \\o "1-3" \\h \\z \\u'); doc.add_page_break()
doc.add_heading('Liste des figures',1); field(doc.add_paragraph().add_run(),'TOC \\h \\z \\c "Figure"'); doc.add_heading('Liste des tableaux',1); field(doc.add_paragraph().add_run(),'TOC \\h \\z \\c "Tableau"')
doc.add_heading('Liste des acronymes',1); add_table(doc,'Tableau 0.1 — Acronymes', [['Sigle','Définition'],['API','Application Programming Interface'],['BPB','Bits per Byte'],['GRU','Gated Recurrent Unit'],['JWT','JSON Web Token'],['MFA','Multi-Factor Authentication'],['TOTP','Time-based One-Time Password'],['XAIC','Conteneur XAI-Compress'],['XAI','Explainable Artificial Intelligence']])

figmap={3:['architecture/system_context.png','architecture/component_architecture.png','architecture/data_flow.png','architecture/deployment.png'],5:['database/erd.png'],6:['ai/compression_pipeline.png'],7:['ai/training_pipeline.png'],8:['security/upload_pipeline.png','security/decompression_pipeline.png','security/auth_sequence.png','security/mfa_sequence.png'],15:['deployment/docker_architecture.png']}
tabmap={2:['Exigences fonctionnelles','Exigences non fonctionnelles'],4:['API principale'],5:['Dictionnaire de données'],8:['Menaces'],16:['Inventaire des tests'],17:['Résultats Hybrid V3'],1:['Technologies']}
figno=1; tabno=1
for ci,(ctitle,sections) in enumerate(chapters):
    doc.add_page_break(); doc.add_heading(ctitle,1); doc.add_paragraph('Introduction du chapitre — Cette partie confronte les concepts aux éléments effectivement présents dans le dépôt et signale les limites de preuve.')
    for st,body in sections:
        doc.add_heading(st,2)
        for para in re.split(r'(?<=\.)\s+(?=[A-ZÉÀL])',body):
            if len(para)>25: doc.add_paragraph(para)
        # add a rigorous analytical paragraph to each substantive section
        doc.add_paragraph("Lecture d’ingénierie. La décision doit être appréciée selon quatre axes: exactitude fonctionnelle, frontière de confiance, coût opérationnel et preuve de validation. Une configuration ou une interface n’est pas assimilée à une exécution de production; inversement, un test ciblé fournit une preuve utile mais circonscrite à son oracle, à ses mocks et à son environnement.")
    chapnum=ci
    if chapnum in figmap:
        for rel in figmap[chapnum]:
            doc.add_picture(str(FIG/rel),width=Inches(6.25)); p=doc.paragraphs[-1]; p.alignment=WD_ALIGN_PARAGRAPH.CENTER
            cap=doc.add_paragraph(f'Figure {figno} — '+Path(rel).stem.replace('_',' ').capitalize(),style='Caption'); cap.alignment=WD_ALIGN_PARAGRAPH.CENTER; figno+=1
            doc.add_paragraph('Interprétation — Le schéma matérialise les dépendances et les points où validation, autorisation ou limitation doivent intervenir.',style='Table Note')
    if chapnum in tabmap:
        for key in tabmap[chapnum]: add_table(doc,f'Tableau {tabno} — {key}',tables[key]); tabno+=1
    if 1<=chapnum<=18: doc.add_heading('Conclusion du chapitre',2); doc.add_paragraph('Les éléments établis dans ce chapitre réduisent l’écart entre architecture annoncée et système démontré. Les limites identifiées alimentent directement les critères de validation et les perspectives, sans être masquées par des formulations promotionnelles.')

doc.add_page_break(); doc.add_heading('Références bibliographiques',1)
refs=['RFC 1951 — DEFLATE Compressed Data Format Specification, IETF, 1996.','RFC 7519 — JSON Web Token (JWT), IETF, 2015.','RFC 6238 — TOTP: Time-Based One-Time Password Algorithm, IETF, 2011.','Cho et al., Learning Phrase Representations using RNN Encoder–Decoder, EMNLP, 2014.','OWASP, Authentication Cheat Sheet et File Upload Cheat Sheet, documentation officielle.','FastAPI, Security and Dependencies, documentation officielle.','Flutter, Secure storage and platform integration, documentation officielle.','Angular, Routing, guards and HTTP interceptors, documentation officielle.','Next.js, Deployment and security documentation, documentation officielle.','PostgreSQL, Constraints, transactions and indexes, documentation officielle.','Docker, Compose specification and secrets, documentation officielle.','ClamAV, clamd and signature database documentation, documentation officielle.','VirusTotal, YARA documentation, documentation officielle.','PyTorch, GRU and reproducibility documentation, documentation officielle.','Google, Brotli format and implementation documentation.']
for r in refs: doc.add_paragraph(r,style='List Number')
doc.add_page_break(); doc.add_heading('Annexes',1)
endpoint_rows=[['Méthode','Endpoint','Contrôle','Finalité']]
for method,path,control,purpose in [
('GET','/health','Public','Vivacité'),('POST','/auth/register','Public','Inscription'),('POST','/auth/login','Public + MFA','Connexion'),('POST','/auth/refresh','Refresh','Renouvellement'),('POST','/auth/logout','Refresh','Révocation'),('GET','/auth/me','JWT','Profil'),('POST','/auth/verification/email/send','JWT','Envoyer code e-mail'),('POST','/auth/verification/email/confirm','JWT','Confirmer e-mail'),('POST','/auth/verification/phone/send','JWT','Envoyer code téléphone'),('POST','/auth/verification/phone/confirm','JWT','Confirmer téléphone'),('POST','/auth/password/forgot','Public','Initier récupération'),('POST','/auth/password/verify-code','Public','Vérifier code'),('POST','/auth/password/reset','Jeton reset','Changer mot de passe'),('GET','/auth/totp/status','JWT','État TOTP'),('POST','/auth/totp/enroll','JWT','Démarrer TOTP'),('POST','/auth/totp/resend','JWT','Renvoyer preuve'),('POST','/auth/totp/email/confirm','JWT','Confirmer canal'),('POST','/auth/totp/confirm','JWT','Activer TOTP'),('POST','/auth/authenticator/enroll/start','JWT','Démarrer appareil'),('POST','/auth/authenticator/enroll/confirm','JWT','Confirmer appareil'),('POST','/auth/devices','JWT','Enregistrer dispositif'),('GET','/auth/devices','JWT','Lister dispositifs'),('POST','/auth/devices/{id}/revoke','JWT','Révoquer dispositif'),('POST','/auth/challenges','JWT','Créer défi'),('GET','/auth/challenges','JWT','Lister défis'),('POST','/auth/challenges/{id}/approve','JWT + dispositif','Approuver'),('POST','/auth/challenges/{id}/reject','JWT + dispositif','Rejeter'),('GET','/auth/history','JWT','Historique auth'),('POST','/auth/recovery-codes','JWT + MFA','Codes de secours'),('POST','/files','JWT','Créer métadonnées'),('POST','/compression/jobs','JWT + scanners','Compresser'),('GET','/files/{id}/download','JWT + propriétaire','Télécharger'),('POST','/compression/decompress','JWT + scanners','Décompresser'),('POST','/files/{id}/email','JWT + propriétaire','Envoyer artefact'),('GET','/email/capabilities','JWT','Capacités e-mail'),('GET','/history','JWT','Historique'),('POST','/shares','JWT + propriétaire','Créer partage'),('GET','/shares','JWT','Lister partages'),('POST','/shares/{id}/revoke','JWT + propriétaire','Révoquer'),('POST','/shares/redeem','JWT destinataire','Racheter'),('GET','/public/shares/{code}','Public assaini','Disponibilité partage'),('POST','/shares/download','JWT destinataire','Télécharger partage'),('GET','/admin/stats','Admin','Statistiques'),('GET','/admin/users','Admin','Utilisateurs'),('GET','/admin/jobs','Admin','Fichiers/jobs'),('GET','/admin/users/{id}','Admin','Détail utilisateur'),('GET','/admin/security/scanner','Admin','État scanners'),('GET','/admin/audit','Admin','Audit'),('GET','/admin/email/configuration','Admin','Configuration assainie'),('GET','/public/status','Public assaini','État services')]: endpoint_rows.append([method,path,control,purpose])
add_table(doc,f'Tableau {tabno} — Inventaire consolidé des endpoints',endpoint_rows); tabno+=1
doc.add_heading('Annexe B — Variables de configuration (sans valeurs)',2); doc.add_paragraph('DATABASE_URL; JWT_SECRET; ACCESS_TOKEN_EXPIRE_MINUTES; REFRESH_TOKEN_EXPIRE_DAYS; CORS_ORIGINS; STORAGE_ROOT; CLAMAV_HOST; CLAMAV_PORT; YARA_RULES_PATH; EMAIL_PROVIDER; SMTP_HOST; SMTP_PORT; SMTP_USERNAME; SMTP_PASSWORD; BREVO_API_KEY; RESEND_API_KEY; PUBLIC_API_URL. Les noms sont documentaires; aucune valeur n’est reproduite.')
add_table(doc,f'Tableau {tabno} — Dictionnaire complet des tables',tables['Dictionnaire de données']); tabno+=1
add_table(doc,f'Tableau {tabno} — Matrice de tests synthétique',tables['Inventaire des tests']); tabno+=1
doc.add_heading('Annexe E — Figures expérimentales à compléter',2)
for item in ['TRAIN-01 — Loss entraînement: epoch/step, train_loss, learning_rate et checkpoint.','TRAIN-02 — Loss validation: epoch, validation_loss et validation_BPB, split figé.','BENCH-01 — BPB par méthode sur les 140 source_id communs.','BENCH-02 — Temps de compression complet, médiane et dispersion par taille.','BENCH-03 — Temps de décompression complet par méthode.','MODEL-01 — Top-k, regret et latence des sélecteurs avec intervalles.']: doc.add_paragraph('[FIGURE À INSÉRER] '+item,style='List Bullet')
doc.add_heading('Annexe F — Placeholders de captures',2)
for s in screens:
    doc.add_page_break()
    doc.add_heading(s[0]+' — '+s[2],3); doc.add_paragraph(f'À capturer : {s[3]}. Éléments visibles : {s[4]}. À masquer : {s[5]}. Recadrage recommandé : fenêtre utile, sans barre personnelle. Légende : Figure [à numéroter] — {s[6]}. Insertion : chapitre {s[7]}. Priorité : {s[8]}.')
    p=doc.add_paragraph('\n\n\n\n\n\n\n\n\n[CAPTURE À INSÉRER — '+s[0]+']\n\n\n\n\n\n\n\n\n')
    p.alignment=WD_ALIGN_PARAGRAPH.CENTER
    p.style='Table Note'

# core properties and save
doc.core_properties.title='Rapport final XAI-Compress'; doc.core_properties.subject='Mémoire technique et académique'; doc.core_properties.author='[À COMPLÉTER]'; doc.core_properties.keywords='XAI-Compress, compression, sécurité, GRU, FastAPI'
docx=OUT/'Rapport_XAI_Compress_Final.docx'; doc.save(docx)

# Markdown source
md=['# Rapport XAI-Compress Final','','> Version factuelle générée à partir du dépôt. Les champs institutionnels et captures restent à compléter.','']
for ct,secs in chapters:
    md += ['# '+ct,'','*Introduction du chapitre.* Les affirmations sont rattachées au code, aux tests, aux configurations ou aux artefacts historiques.','']
    for st,b in secs: md += ['## '+st,'',b,'',"**Lecture d’ingénierie.** Exactitude, confiance, coût et preuve sont distingués; une configuration n’est pas une preuve de production.",'']
    md += ['## Conclusion du chapitre','','Les résultats et limites sont conservés explicitement.','']
md += ['# Bibliographie','']+['- '+r for r in refs]+['','# Annexes','','Les inventaires complets se trouvent dans le DOCX, le fichier de preuves et la checklist de captures.']
(OUT/'Rapport_XAI_Compress_Source.md').write_text('\n'.join(md),encoding='utf-8')

# checklist
lines=['# SCREENSHOT CHECKLIST','','Ne jamais afficher OTP, secret TOTP, token, mot de passe, clé API, chaîne de base ou e-mail réel.','', '| ID | Application | Écran | Étapes | Visible | À masquer | Légende | Chapitre | Priorité |','|---|---|---|---|---|---|---|---:|---|']
for s in screens: lines.append('| '+' | '.join(s)+' |')
(OUT/'SCREENSHOT_CHECKLIST.md').write_text('\n'.join(lines),encoding='utf-8')

# evidence and gaps
ev=['# REPORT EVIDENCE','','## Analyse de Rapport Houssem','','Référence: `rapport-pfe/Rapport_PFE_Saada_HoussemEddine.pdf`, 113 pages. Structure observée: couverture et autorisation de dépôt; dédicace; remerciements; table des matières; listes des figures et tableaux; introduction générale; cinq chapitres avec introduction/conclusion; conclusion générale; bibliographie. Le rapport compte de nombreuses figures et tables et suit une numérotation académique. Cette structure a guidé le front matter, la progression, les légendes et les conclusions; aucun texte projet n’a été copié.','','## Matrice des affirmations','','| Affirmation | Preuve | Confiance |','|---|---|---|']
for a,p,c in evidence: ev.append(f'| {a} | `{p}` | {c} |')
(OUT/'REPORT_EVIDENCE.md').write_text('\n'.join(ev),encoding='utf-8')
gaps='''# REPORT GAPS

## BLOCKING BEFORE SUBMISSION

- Nom complet de l’auteur, établissement, formation, encadrants et année universitaire.
- Logos officiels et page d’autorisation conforme à l’établissement.
- Captures MANDATORY assainies, dont scanner et services Docker.
- Preuve d’un déploiement coordonné récent et round-trip authentifié sur production.
- Validation MFA sur téléphone physique et réception e-mail réelle.
- Politique finale de confidentialité, rétention, suppression et identité du responsable.
- Artefacts mobiles/desktop signés et test d’installation propre si distribués.

## IMPORTANT

- Courbes d’entraînement issues des historiques retenus et intervalles de benchmark.
- Caractéristiques matérielles exactes du benchmark V3.
- Tests Angular exécutables et projet de tests Admin .NET.
- Mesure mémoire isolée par codec et tests sur davantage d’audio/médias.
- Relecture académique des citations et adaptation au style bibliographique exigé.

## OPTIONAL

- Dédicaces et remerciements personnalisés.
- Gantt final, captures de CI/CD et monitoring.
- Étude utilisateur UX et comparaison énergétique CPU/GPU.
'''
(OUT/'REPORT_GAPS.md').write_text(gaps,encoding='utf-8')

# sanitized evidence snippets, values deliberately omitted
(EVI/'audit_summary.txt').write_text('Source audit: 43 API routes; 12 ORM tables; source test definitions backend=124, engine=146, desktop=36, Angular=24, mobile=12. Hybrid V3 artifact: 140 held-out files, 368446658 original bytes, selected hybrid_v3_top3. No secrets copied.\n',encoding='utf-8')

# Submission-ready PDF. ReportLab is used because the installed Word PDF
# exporter blocks headlessly on this workstation. The PDF is generated from
# the same content model, with deterministic page furniture and pagination.
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle, Image as RLImage, KeepTogether

pdf=OUT/'Rapport_XAI_Compress_Final.pdf'
ss=getSampleStyleSheet()
ss.add(ParagraphStyle(name='FRBody',parent=ss['BodyText'],fontName='Helvetica',fontSize=9.4,leading=12.1,alignment=TA_JUSTIFY,spaceAfter=6))
ss.add(ParagraphStyle(name='FRH1',parent=ss['Heading1'],fontName='Helvetica-Bold',fontSize=17,leading=20,textColor=colors.HexColor('#17365D'),spaceAfter=11))
ss.add(ParagraphStyle(name='FRH2',parent=ss['Heading2'],fontName='Helvetica-Bold',fontSize=12.5,leading=15,textColor=colors.HexColor('#2E75B6'),spaceBefore=8,spaceAfter=5))
ss.add(ParagraphStyle(name='FRSmall',parent=ss['BodyText'],fontName='Helvetica-Oblique',fontSize=8,leading=10,textColor=colors.HexColor('#666666'),spaceAfter=5))
ss.add(ParagraphStyle(name='FRCover',parent=ss['Title'],fontName='Helvetica-Bold',fontSize=22,leading=28,alignment=TA_CENTER,textColor=colors.HexColor('#17365D'),spaceAfter=18))
def esc(s):
    s=str(s).replace('σ','sigmoid').replace('⊙','.*').replace('×','x')
    return s.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')
def on_page(canvas,doc_):
    canvas.saveState(); canvas.setStrokeColor(colors.HexColor('#D9E2F3')); canvas.line(1.7*cm,1.35*cm,19.3*cm,1.35*cm)
    canvas.setFont('Helvetica',7.5); canvas.setFillColor(colors.HexColor('#666666')); canvas.drawString(1.7*cm,1.0*cm,'XAI-COMPRESS | MÉMOIRE TECHNIQUE'); canvas.drawRightString(19.3*cm,1.0*cm,str(doc_.page)); canvas.restoreState()
story=[Spacer(1,3*cm),Paragraph('[LOGO UNIVERSITÉ / ÉCOLE] &nbsp;&nbsp;&nbsp;&nbsp; [LOGO ENTREPRISE / LABORATOIRE]',ss['FRSmall']),Spacer(1,1.2*cm),Paragraph('CONCEPTION ET DÉVELOPPEMENT D’UNE PLATEFORME INTELLIGENTE ET SÉCURISÉE DE COMPRESSION DE DONNÉES BASÉE SUR L’INTELLIGENCE ARTIFICIELLE',ss['FRCover']),Paragraph('XAI-COMPRESS',ss['FRCover']),Spacer(1,.8*cm)]
for line in ['Mémoire de projet de fin d’études','[ÉTABLISSEMENT] — [FORMATION]','Auteur : [À COMPLÉTER]','Encadrant(s) : [À COMPLÉTER]','Année universitaire : [À COMPLÉTER]']: story.append(Paragraph(esc(line),ParagraphStyle('center',parent=ss['FRBody'],alignment=TA_CENTER)))
story += [PageBreak(),Paragraph('Dédicaces',ss['FRH1']),Paragraph('[À COMPLÉTER — texte personnel facultatif]',ss['FRBody']),Spacer(1,2*cm),Paragraph('Remerciements',ss['FRH1']),Paragraph('[À COMPLÉTER — établissement, encadrants, équipe et jury]',ss['FRBody']),PageBreak(),Paragraph('Résumé',ss['FRH1']),Paragraph("Ce mémoire présente XAI-Compress, une plate-forme multi-client de compression sans perte associant sélection hybride de codecs, API FastAPI, clients Next.js, Angular, Flutter et .NET, PostgreSQL et contrôles ClamAV/YARA. L’étude montre que Hybrid V3 top-3 améliore fortement le débit face à Brotli-11 sur 140 fichiers, tout en restant 0,7591 % plus volumineux. L’apport majeur est l’intégration vérifiable du routage adaptatif, de l’intégrité SHA-256, du MFA TOTP et du fail-closed.",ss['FRBody']),Paragraph('Abstract',ss['FRH1']),Paragraph("This report presents XAI-Compress, a multi-client lossless-compression platform combining hybrid codec selection, FastAPI, Next.js, Angular, Flutter, .NET, PostgreSQL, and ClamAV/YARA controls. Hybrid V3 top-3 greatly improves compression throughput over Brotli-11 on 140 held-out files while producing a 0.7591% larger artifact.",ss['FRBody']),PageBreak(),Paragraph('Table des matières — structure',ss['FRH1'])]
for i,(ct,_) in enumerate(chapters): story.append(Paragraph(f'{i}. {esc(ct)}',ss['FRBody']))
story += [PageBreak(),Paragraph('Liste des figures et tableaux',ss['FRH1']),Paragraph(f'{len(diagrams)} figures techniques générées; 11 tableaux principaux et annexes détaillées.',ss['FRBody']),Paragraph('Liste des acronymes',ss['FRH1'])]
story.append(Table(tables['Exigences non fonctionnelles'][:1]+[['API','Application Programming Interface'],['BPB','Bits per Byte'],['GRU','Gated Recurrent Unit'],['JWT','JSON Web Token'],['MFA','Multi-Factor Authentication'],['TOTP','Time-based One-Time Password'],['XAIC','Conteneur XAI-Compress']],colWidths=[3*cm,13*cm],style=[('BACKGROUND',(0,0),(-1,0),colors.HexColor('#17365D')),('TEXTCOLOR',(0,0),(-1,0),colors.white),('GRID',(0,0),(-1,-1),.3,colors.grey),('FONT',(0,0),(-1,-1),'Helvetica',8),('VALIGN',(0,0),(-1,-1),'TOP')]))

fig_by_ch={3:figmap[3],5:figmap[5],6:figmap[6],7:figmap[7],8:figmap[8],15:figmap[15]}
table_by_ch=tabmap
pdf_tabno=1; pdf_figno=1
for ci,(ct,secs) in enumerate(chapters):
    story += [PageBreak(),Paragraph(esc(ct),ss['FRH1']),Paragraph('<i>Introduction du chapitre.</i> Cette partie confronte les concepts aux éléments réellement observés et conserve les limites de preuve.',ss['FRBody'])]
    for st,b in secs:
        story.append(Paragraph(esc(st),ss['FRH2']))
        # Split into readable paragraphs and preserve enough depth.
        pieces=re.split(r'(?<=\.)\s+(?=[A-ZÉÀL])',b)
        for piece in pieces:
            if len(piece)>20: story.append(Paragraph(esc(piece),ss['FRBody']))
        story.append(Paragraph('<b>Lecture d’ingénierie.</b> La décision est évaluée selon l’exactitude fonctionnelle, la frontière de confiance, le coût opérationnel et la preuve de validation. Une configuration n’est pas assimilée à une exécution de production.',ss['FRSmall']))
    if ci in table_by_ch:
        for key in table_by_ch[ci]:
            data=[[Paragraph('<b>'+esc(x)+'</b>',ss['FRSmall']) for x in tables[key][0]]]+[[Paragraph(esc(x),ss['FRSmall']) for x in row] for row in tables[key][1:]]
            story += [Spacer(1,.2*cm),Paragraph(f'Tableau {pdf_tabno} — {esc(key)}',ss['FRSmall']),Table(data,repeatRows=1,colWidths=[17.3*cm/len(data[0])]*len(data[0]),style=TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#17365D')),('TEXTCOLOR',(0,0),(-1,0),colors.white),('GRID',(0,0),(-1,-1),.25,colors.HexColor('#9AA7B4')),('VALIGN',(0,0),(-1,-1),'TOP'),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#F3F6F9')]),('LEFTPADDING',(0,0),(-1,-1),4),('RIGHTPADDING',(0,0),(-1,-1),4)])),Paragraph('Interprétation — La synthèse est circonscrite aux preuves indiquées.',ss['FRSmall'])]; pdf_tabno+=1
    story += [Paragraph('Conclusion du chapitre',ss['FRH2']),Paragraph('Les résultats établis réduisent l’écart entre système annoncé et système démontré. Les limites alimentent les critères de validation et les perspectives.',ss['FRBody'])]
    if ci in fig_by_ch:
        for rel in fig_by_ch[ci]:
            story += [PageBreak(),Paragraph(f'Figure {pdf_figno} — {Path(rel).stem.replace("_"," ").capitalize()}',ss['FRH2']),RLImage(str(FIG/rel),width=17.2*cm,height=9.36*cm),Spacer(1,.3*cm),Paragraph('Interprétation — Le diagramme matérialise les responsabilités, dépendances et frontières où les contrôles doivent intervenir.',ss['FRBody'])]; pdf_figno+=1

story += [PageBreak(),Paragraph('Références bibliographiques',ss['FRH1'])]
for i,r in enumerate(refs,1): story.append(Paragraph(f'[{i}] {esc(r)}',ss['FRBody']))
story += [PageBreak(),Paragraph('Annexe A — Inventaire consolidé des endpoints',ss['FRH1'])]
edata=[[Paragraph('<b>'+esc(x)+'</b>',ss['FRSmall']) for x in endpoint_rows[0]]]+[[Paragraph(esc(x),ss['FRSmall']) for x in row] for row in endpoint_rows[1:]]
story.append(Table(edata,repeatRows=1,colWidths=[2*cm,7.2*cm,3.4*cm,4.7*cm],style=TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#17365D')),('TEXTCOLOR',(0,0),(-1,0),colors.white),('GRID',(0,0),(-1,-1),.25,colors.grey),('VALIGN',(0,0),(-1,-1),'TOP'),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#F3F6F9')])])))
story += [PageBreak(),Paragraph('Annexe B — Preuves principales',ss['FRH1'])]
for a,p,c in evidence: story += [Paragraph('<b>'+esc(a)+'</b>',ss['FRH2']),Paragraph('Preuve: '+esc(p),ss['FRBody']),Paragraph('Confiance: '+esc(c),ss['FRSmall'])]
story += [PageBreak(),Paragraph('Annexe C — Figures expérimentales à compléter',ss['FRH1'])]
for idx,item in enumerate(['Loss entraînement: epoch/step, train_loss, learning_rate, checkpoint.','Loss validation: epoch, validation_loss, validation_BPB et split.','BPB par méthode sur les 140 source_id communs.','Temps complet de compression et dispersion par taille.','Temps complet de décompression par méthode.','Top-k, regret et latence des sélecteurs avec intervalles.']):
    if idx: story.append(PageBreak())
    story += [Paragraph(f'Figure expérimentale E-{idx+1}',ss['FRH1']),Paragraph('[RÉSULTAT EXPÉRIMENTAL À INSÉRER] '+esc(item),ss['FRBody']),Spacer(1,13*cm),Paragraph('Données minimales attendues: identifiant de source, taille originale, méthode, répétition, temps complet, octets finaux, statut SHA-256 et environnement. La visualisation devra afficher la dispersion et non seulement une moyenne.',ss['FRSmall'])]
story += [PageBreak(),Paragraph('Annexe D — Configuration sans valeurs',ss['FRH1']),Paragraph('DATABASE_URL; JWT_SECRET; ACCESS_TOKEN_EXPIRE_MINUTES; REFRESH_TOKEN_EXPIRE_DAYS; CORS_ORIGINS; STORAGE_ROOT; CLAMAV_HOST; CLAMAV_PORT; YARA_RULES_PATH; EMAIL_PROVIDER; SMTP_HOST; SMTP_PORT; SMTP_USERNAME; SMTP_PASSWORD; BREVO_API_KEY; RESEND_API_KEY; PUBLIC_API_URL.',ss['FRBody']),Paragraph('Aucune valeur n’est reproduite. La présence d’un nom de variable ne prouve ni sa définition ni sa rotation en production.',ss['FRSmall']),PageBreak(),Paragraph('Annexe E — Limites avant soumission',ss['FRH1'])]
for x in ['Déploiement coordonné et round-trip authentifié non prouvés.','MFA à valider sur téléphone physique avec e-mail réel.','Applications à signer et installer proprement.','Politique de rétention, suppression et confidentialité à finaliser.','Courbes d’entraînement et environnement matériel du benchmark à insérer.','Tests Angular exécutables et projet de tests Admin .NET à établir.']: story.append(Paragraph('• '+esc(x),ss['FRBody']))
story += [PageBreak(),Paragraph('Annexe F — Porte de qualité finale',ss['FRH1'])]
for x in ['Source et migrations alignées','Aucun secret dans les artefacts','SHA-256 round-trip','ClamAV et YARA opérationnels','MFA physique validé','Builds signés','Tests clients exécutés','Captures assainies','Références relues','Champs institutionnels complétés']: story.append(Paragraph('[ ] '+esc(x),ss['FRBody']))
for s in screens:
    story += [PageBreak(),Paragraph(esc(s[0]+' — '+s[2]),ss['FRH1']),Paragraph('<b>À capturer:</b> '+esc(s[3]),ss['FRBody']),Paragraph('<b>Visible:</b> '+esc(s[4]),ss['FRBody']),Paragraph('<b>À masquer:</b> '+esc(s[5]),ss['FRBody']),Spacer(1,5.5*cm),Paragraph('[CAPTURE À INSÉRER — '+esc(s[0])+']',ParagraphStyle('box',parent=ss['FRCover'],fontSize=15,textColor=colors.HexColor('#8795A1'))),Spacer(1,5.5*cm),Paragraph('Légende proposée — '+esc(s[6])+'. Chapitre '+esc(s[7])+'. Priorité '+esc(s[8])+'.',ss['FRSmall'])]

SimpleDocTemplate(str(pdf),pagesize=A4,rightMargin=1.7*cm,leftMargin=1.7*cm,topMargin=1.7*cm,bottomMargin=1.7*cm,title='Rapport XAI-Compress Final',author='[À COMPLÉTER]').build(story,onFirstPage=on_page,onLaterPages=on_page)
print(docx)
print(pdf)
print('figures',len(diagrams),'tables',tabno-1,'screens',len(screens))

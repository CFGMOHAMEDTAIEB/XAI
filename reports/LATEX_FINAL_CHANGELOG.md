# Journal de révision académique finale du rapport XAI-Compress

Date de clôture : 26 septembre 2026  
Racine LaTeX : `C:\Users\ss\Desktop\XAI\last-Pro-Report`

## Résultat

- Le mémoire existant a été révisé sans être recréé.
- Le PDF final contient 78 pages, soit moins que la limite imposée de 80 pages.
- Le document utilise une taille principale de 11 pt.
- Le sommaire, la liste des figures, la liste des tableaux, la bibliographie et les annexes sont présents.
- Le PDF contient 32 figures, 11 tableaux et 23 entrées bibliographiques.
- Empreinte SHA-256 du PDF final : `7141623D9577ACD0177799A5C7DC139F9F8BB558AC84FD67BD14EB3076D3CCF3`.

## Révisions de fond

- Réécriture des résumés français et anglais pour distinguer le sélecteur Hybrid V3 de la voie neuronale GRU expérimentale.
- Condensation et correction de l'état de l'art : compression sans perte, Huffman, Lempel--Ziv, DEFLATE, Brotli, Zstandard, entropie, GRU et codage arithmétique.
- Réécriture de la partie IA afin d'éviter de présenter le GRU expérimental comme le mécanisme de routage déployé.
- Remplacement de la validation générique par les preuves actuelles : campagnes de tests, benchmark de 140 fichiers, métriques du sélecteur et scénario E2E réel à deux utilisateurs.
- Ajout du schéma PostgreSQL vérifié à 13 tables et clarification de la séparation métadonnées/stockage d'artefacts.
- Réécriture de la chaîne de sécurité des fichiers selon le comportement observé : SHA-256, ClamAV, YARA, autorisation et politique fail-closed.
- Remplacement de la conclusion et des perspectives redondantes par une conclusion unique, factuelle et limitée aux preuves disponibles.
- Maintien explicite des limites : dépendances vulnérables non remédiées, paquets de diffusion non signés, asymétrie de répétition du benchmark et absence de preuve de production.

## Résultats scientifiques conservés

- Corpus du benchmark : 140 fichiers, 368 446 658 octets originaux par méthode.
- Hybrid V3 : 362 188 760 octets, 7,864124 BPB, 18,027349 MiB/s en compression et 32,202720 MiB/s en décompression.
- Brotli-11 : 359 459 933 octets ; l'écart agrégé de V3 est de 2 728 827 octets, soit environ 0,759 %, avec un débit de compression environ 71,73 fois supérieur dans ce protocole.
- Sélecteur : top-1 0,666667 ; top-2 0,810753 ; top-3 0,890323 ; latence moyenne 0,325453 ms.
- E2E : 305 -> 257 -> 305 octets et SHA-256 final identique à l'original.
- Tests conservés : FastAPI 166 ; moteur 206 réussis et 4 ignorés ; Rust 2 ; Angular 24 ; Next.js 8 avec lint/typecheck/build ; Flutter Desktop 37 réussis et 2 ignorés ; Flutter Mobile 22 ; .NET 2 scénarios d'intégration.

## Visuels

- Ajout de `images/screenshots/fig_compression_success.png` depuis la preuve authentique assainie du dépôt.
- Ajout de `images/screenshots/fig_sha256_roundtrip.png` depuis la preuve authentique assainie du dépôt.
- Aucun visuel externe n'a été ajouté ; aucune attribution de licence supplémentaire n'est donc requise.
- Les schémas de cible ou de proposition sont explicitement qualifiés comme conceptions de l'auteur.

## Recherche externe et bibliographie

- Vérification auprès de sources primaires ou officielles : RFC 7932, NIST FIPS 180-4, publication ACL de Cho et al. sur le GRU et publication ACM sur le codage arithmétique.
- Correction des métadonnées de la référence `cho2014`.
- Suppression des entrées non nécessaires ou non vérifiables `nguyenStructure`, `dhaouadi2026neuralshield` et `scrumguide2020`.
- Aucune nouvelle figure externe et aucune nouvelle entrée bibliographique non utilisée n'ont été introduites.

## Fichiers LaTeX principaux modifiés ou ajoutés

- `main.tex`
- `config/info.tex`
- `config/preamble.tex`
- `frontmatter/acknowledgements.tex`
- `frontmatter/resume.tex`
- `chapters/introduction_generale.tex`
- `chapters/chapter2_etat_art.tex`
- `chapters/chapter3_release1.tex`
- `chapters/chapter4_release2.tex`
- `chapters/chapter5_validation.tex`
- `chapters/conclusion_finale.tex`
- `content/etat_art_body.tex`
- `content/ai_demoted.tex`
- `content/impl_database_final.tex`
- `content/impl_security_final.tex`
- `content/method_selected.tex`
- `content/validation_final.tex`
- `bibliography/references.bib`
- `images/screenshots/fig_compression_success.png`
- `images/screenshots/fig_sha256_roundtrip.png`
- `main.pdf`

## Contrôles LaTeX et visuels

- Compilation multi-passe réussie avec Tectonic 0.17.0 et le backend BibTeX compatible avec cet environnement portable.
- Nombre de pages vérifié par lecture structurelle du PDF : 78.
- Texte extrait vérifié : bibliographie présente, aucun marqueur `??`.
- Journal final vérifié : aucune citation ou référence croisée individuellement indéfinie, aucune bibliographie vide, aucun `Overfull \\hbox`.
- Les 78 pages ont été rendues en PNG ; des planches de contact et des rendus détaillés ont été inspectés.
- Pages contrôlées en priorité : couverture, résumés, sommaire, listes, débuts de chapitres, tableaux, architecture, IA, base de données, sécurité, benchmark, E2E, captures de preuve, conclusion, bibliographie et annexes.
- Les avertissements résiduels concernent le backend BibTeX de repli de `biblatex`, des espaces typographiques invisibles U+200B et quelques boîtes insuffisamment remplies ; ils ne produisent ni texte manquant visible ni débordement de page.

## TODO laissés volontairement

- Université/école et département/filière.
- Nom de l'étudiant.
- Organisme d'accueil.
- Encadrant académique et encadrant professionnel.
- Intitulé administratif exact du diplôme si différent de la valeur générique actuelle.

Ces informations n'étaient pas vérifiables dans le dépôt et doivent être complétées par l'auteur avant dépôt institutionnel.

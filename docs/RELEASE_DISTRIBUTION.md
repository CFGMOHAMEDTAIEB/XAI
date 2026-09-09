# Release distribution gate

Status: PARTIAL infrastructure; production distribution BLOCKED. No artifacts were uploaded.

Use the existing repository, `CFGMOHAMEDTAIEB/XAI`, and its version-tagged GitHub Releases assets. No additional storage service is required. The website reads `apps/public_nextjs/lib/releases.json`; it currently contains no releases. `productionReleases()` rejects missing metadata, test channels, unsigned/unverified signing, missing installation evidence flags, malformed checksums and non-repository URLs. Invalid metadata produces unavailable UI rather than a fabricated link.

The metadata gate is a publication filter, not cryptographic proof. Reviewers must not mark signing or installation VERIFIED/PASSED based only on a build exit code. Full automated signing/publishing remains blocked on operator-owned signing material, installation devices and release approval. The existing `scripts/build_production.ps1` produces local evidence with paths; those private build reports must never be copied directly to the public manifest.

## Required release procedure

1. Build from a reviewed source revision using the existing build script and an actual API origin. Preserve Android's release-signing failure when keys are absent; never enable debug signing for public production.
2. Android: verify the final APK with the SDK `apksigner verify --verbose --print-certs`, match its signing certificate to the approved release certificate, and install/test it on the intended device. A successful signature check alone does not distinguish an approved certificate from a debug certificate. Resolve the current `com.example` package identifier before store distribution.
3. Windows: sign the installer/executables with the approved publisher certificate and timestamp; verify Authenticode for shipped executables and installer. A ZIP itself is not a signed Windows executable. Test installation, login, MFA, processing, update/removal on a clean target machine. The current unsigned folder/ZIP is TEST only.
4. iOS/macOS require Apple signing, provisioning/notarization as appropriate and target-device testing. No such release evidence exists in this audit. Linux/CLI also have no approved public release manifest.
5. Record version from the actual package, target platform/architecture, filename, release date, byte size, SHA-256, signing verification, installation test evidence and release notes. Archive verification output and source revision in the release review, without signing secrets.
6. Publish the approved artifact as a version-tagged repository release asset only after release approval. Download the hosted asset and compare its SHA-256/size to the approved artifact. A URL returning HTML or redirecting to a login page is not a valid artifact.
7. Add one reviewed manifest entry per platform (the website displays the first approved entry for each platform), using fields below. Run `node --test tests/*.test.mjs`, lint, typecheck and production build in the public app, then deploy and verify the live download bytes and checksum.

## Manifest schema

Root: `schemaVersion: 1`, `releases: []`.

Each entry requires `platform` (`android`, `windows`, `ios`, `macos`, `linux`, `cli`), `version`, `filename`, `architecture`, `releasedAt` (ISO date/time), `sizeBytes` (positive integer), `sha256` (64 hex characters), `releaseNotes`, `url` (version-tagged asset in the existing GitHub repository), `channel: PRODUCTION`, `signing: VERIFIED`, `installTest: PASSED`.

Do not add an entry until every prerequisite is evidenced. Do not invent versions, dates, hashes, URLs or signing statements. No example artifact is included in the production manifest. Test fixtures exist only under the test directory.

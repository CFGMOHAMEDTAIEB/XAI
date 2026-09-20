# Dependency security

Current non-destructive audits were run against the lockfiles on 2026-09-20. No automatic fix or major upgrade was applied. Passing builds, tests, and runtime checks do not imply dependency-security clearance.

## Angular

`npm audit --json` reported 23 vulnerable package groups: 12 high, 9 moderate, 2 low, 0 critical. Most are development/build-chain dependencies, but they remain relevant when development servers or build inputs are exposed to untrusted content.

| PACKAGE | SEVERITY | DIRECT/TRANSITIVE | FIX AVAILABLE | BREAKING RISK | RECOMMENDED ACTION |
| --- | --- | --- | --- | --- | --- |
| `@angular-devkit/build-angular` | high | direct | yes, 20.3.37 | low/moderate; non-major | Upgrade with matching Angular toolchain and rerun test/build. |
| `@angular/cli` | high | direct | yes, 20.3.37 | low/moderate; non-major | Upgrade with build-angular. |
| `vitest` / `@vitest/mocker` | moderate | direct + transitive | yes, Vitest 5.0.1 | high; major | Plan a test-runner migration and rerun all tests. |
| `@angular/build`, `vite` | high | transitive | yes through Angular builder | moderate | Upgrade the Angular builder set together. |
| `http-proxy-middleware` | high | transitive | yes | low/moderate | Resolve through the Angular builder update. |
| `fast-uri` | high | transitive | yes | low | Refresh lockfile through supported parent versions. |
| `image-size`, `less` | high | transitive | yes through Angular builder | moderate | Resolve through the Angular builder update. |
| `js-yaml` | high | transitive | yes | low | Refresh to a patched transitive version. |
| `pacote` | high | transitive | yes through Angular CLI | moderate | Upgrade Angular CLI. |
| `piscina` | high | transitive | yes through Angular builder | moderate | Upgrade Angular builder and verify build isolation. |
| `postcss` | high | transitive | yes through Angular builder | moderate | Upgrade Angular builder and rerun CSS builds. |
| `body-parser`, `express`, `qs` | moderate | transitive | yes | low/moderate | Refresh webpack-dev-server dependency chain. |
| `hono` | moderate | transitive | yes | low/moderate | Refresh the parent package and lockfile. |
| `sockjs`, `uuid`, `webpack-dev-server` | moderate | transitive | yes through Angular builder | moderate | Upgrade builder/dev server; avoid exposing dev server publicly. |
| `@babel/core`, `esbuild` | low | transitive | yes through Angular builder | low/moderate | Upgrade the Angular builder set. |

## Next.js

`npm audit --json` reported 4 vulnerable package groups: 1 critical and 3 high.

| PACKAGE | SEVERITY | DIRECT/TRANSITIVE | FIX AVAILABLE | BREAKING RISK | RECOMMENDED ACTION |
| --- | --- | --- | --- | --- | --- |
| `next` | critical | direct | yes | moderate/high; framework upgrade | Upgrade to a patched supported Next.js release immediately, then rerun unit, lint, typecheck, build, route, and download tests. Do not expose the current build as production-ready. |
| `js-yaml` | high | transitive | yes | low | Refresh the resolved transitive version. |
| `postcss` | high | transitive through Next.js | yes | moderate | Resolve through the supported Next.js dependency set. |
| `sharp` | high | transitive through Next.js | yes | moderate; native image stack | Upgrade with Next.js and validate image handling on Windows and container Linux. |

## Python

`pip-audit` is not installed in the project analysis environment and no configured Python dependency-audit command was found. Python vulnerability auditing is **NOT_TESTED**; ordinary pytest success is not a substitute.

## .NET

`dotnet list ... package --vulnerable --include-transitive` exited 0 and listed no vulnerable package. The same command emitted NU1900 because live NuGet vulnerability metadata could not be loaded reliably. Treat this as **BLOCKED for authoritative live advisory clearance**, not as proof that the dependency graph is vulnerability-free.

## Acceptance impact

Dependency security is **FAIL** for release acceptance while the direct critical Next.js finding and Angular high findings remain unresolved. The project must not be called production-ready on the basis of current build/test/runtime passes.

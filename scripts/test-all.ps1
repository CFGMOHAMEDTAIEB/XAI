[CmdletBinding()]
param()
$ErrorActionPreference='Continue'
$root=Split-Path $PSScriptRoot -Parent;$logs=Join-Path $root '.xai-runtime/test-logs';New-Item -ItemType Directory -Path $logs -Force|Out-Null
$results=@()
function Campaign($component,$command,$defined,$environment,[scriptblock]$run){
 $log=Join-Path $logs (($component-replace '[^A-Za-z0-9.-]','-')+'.log');Write-Host "=== $component ==="
 & $run 2>&1|Tee-Object -FilePath $log;$exit=$LASTEXITCODE;$text=Get-Content $log -Raw
 $passed=0;$failed=0;$skipped=0
 if($text -match '(\d+) passed'){$passed=[int]$Matches[1]};if($text -match '(\d+) failed'){$failed=[int]$Matches[1]};if($text -match '(\d+) skipped'){$skipped=[int]$Matches[1]}
 if($text -match '# pass (\d+)'){$passed=[int]$Matches[1]}
 if($text -match 'Tests\s+(\d+) passed'){$passed=[int]$Matches[1]}
 if($text -match '\+(\d+) ~?(\d+)?: All tests passed!'){$passed=[int]$Matches[1];if($Matches[2]){$skipped=[int]$Matches[2]}}
 if($text -match 'All tests passed!' -and $text -match '\+(\d+)'){$passed=[int]$Matches[1]}
 if($text -match 'ADMIN_CLIENT_ERROR_TESTS\s*=\s*PASS' -and $text -match 'ADMIN LOGIN, MFA, ROLE AND LOGOUT TESTS\s*=\s*PASS'){$passed=2}
 $script:results += [pscustomobject]@{Component=$component;Command=$command;Defined=$defined;Executed='YES';Passed=$passed;Failed=$(if($exit){[math]::Max(1,$failed)}else{$failed});Skipped=$skipped;Blocked=0;Environment=$environment;Notes=$(if($exit){"FAIL exit=$exit"}else{'PASS'})}
}
$repoMount="type=bind,source=$root,target=/repo,readonly"
Campaign 'FastAPI' 'pytest services/api_fastapi/tests' 166 'Docker Python 3.12, network none' { docker run --rm --network none --mount $repoMount --workdir /repo/services/api_fastapi --env PYTHONPATH=/repo/services/api_fastapi:/opt/xai-compress --env DATABASE_URL=sqlite:///:memory: --env STORAGE_PATH=/tmp/xai-tests xai-backend python -m pytest tests -q -p no:cacheprovider --basetemp=/tmp/xai-api-tests }
$engine=Join-Path $root 'engines/XAI-Compress';$python=Join-Path $root '.venv/Scripts/python.exe';$engineTemp=Join-Path ([IO.Path]::GetTempPath()) ('xai-engine-pytest-'+[guid]::NewGuid().ToString('N'))
Campaign 'Engine Python' 'python -m pytest -q' 210 'Host analysis venv; unique OS temp directory' { Push-Location $engine;try{& $python -m pytest -q -p no:cacheprovider --basetemp $engineTemp}finally{Pop-Location} }
Campaign 'Rust core' 'cargo test' 2 'Host Rust toolchain; stable ABI forward compatibility' { $old=$env:PYO3_USE_ABI3_FORWARD_COMPATIBILITY;$env:PYO3_USE_ABI3_FORWARD_COMPATIBILITY='1';try{& cargo test --manifest-path (Join-Path $engine 'rust-core/Cargo.toml')}finally{$env:PYO3_USE_ABI3_FORWARD_COMPATIBILITY=$old} }
Campaign 'Angular' 'npm.cmd test' 24 'Host Node/Vitest' { Push-Location (Join-Path $root 'apps/web_angular');try{& npm.cmd test}finally{Pop-Location} }
Campaign 'Next.js unit' 'node --test tests/*.test.mjs' 8 'Host Node' { Push-Location (Join-Path $root 'apps/public_nextjs');try{& node --test tests/*.test.mjs}finally{Pop-Location} }
Campaign 'Next.js quality/build' 'npm lint + typecheck + build' 'build checks' 'Host Node/Next' { Push-Location (Join-Path $root 'apps/public_nextjs');try{& npm.cmd run lint;if($LASTEXITCODE){return};& npm.cmd run typecheck;if($LASTEXITCODE){return};& npm.cmd run build}finally{Pop-Location} }
Campaign 'Flutter Desktop' 'flutter test' 39 'Host Flutter Windows' { Push-Location (Join-Path $root 'apps/desktop_flutter');try{& flutter.bat test}finally{Pop-Location} }
Campaign 'Flutter Mobile' 'flutter test' 22 'Host Flutter' { Push-Location (Join-Path $root 'apps/mobile_authenticator_flutter');try{& flutter.bat test}finally{Pop-Location} }
Campaign '.NET Admin' 'dotnet run AdminIntegrationTests' 2 'Host .NET 10 SDK / net8 target' { & dotnet run --project (Join-Path $root 'tools/admin_integration_tests/AdminIntegrationTests.csproj') --artifacts-path (Join-Path $root '.xai-runtime/dotnet-admin-tests') }
$report=@('# Current test report','',"Generated: $((Get-Date).ToUniversalTime().ToString('o'))",'', '| COMPONENT | COMMAND | DEFINED/DISCOVERED | EXECUTED | PASSED | FAILED | SKIPPED | BLOCKED | ENVIRONMENT | NOTES |','| --- | --- | ---: | --- | ---: | ---: | ---: | ---: | --- | --- |')
foreach($row in $results){$report+='| '+(($row.Component,$row.Command,$row.Defined,$row.Executed,$row.Passed,$row.Failed,$row.Skipped,$row.Blocked,$row.Environment,$row.Notes)-join ' | ')+' |'}
$report+=@('','Counts are from this run only. Build checks are listed separately and are not treated as runtime tests. Mocked/unit coverage is not production or device evidence.')
[IO.File]::WriteAllLines((Join-Path $root 'reports/TEST_REPORT.md'),$report,[Text.UTF8Encoding]::new($false))
if(@($results|Where-Object Failed -gt 0).Count){exit 1}

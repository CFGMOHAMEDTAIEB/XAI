[CmdletBinding()]
param()
$ErrorActionPreference='Continue'
$root=(Resolve-Path (Split-Path $PSScriptRoot -Parent)).Path
$targets=@('services/api_fastapi/.pytest_cache','scripts/__pycache__','apps/web_angular/dist','apps/public_nextjs/.next','apps/admin_dotnet/bin','apps/admin_dotnet/obj')
foreach($relative in $targets){$full=[IO.Path]::GetFullPath((Join-Path $root $relative));if(-not $full.StartsWith($root+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)){throw 'Unsafe cleanup target'};if(Test-Path -LiteralPath $full){$tracked=(git -C $root ls-files -- $relative|Measure-Object).Count;if($tracked){Write-Warning "Kept tracked $relative"}else{try{Remove-Item -LiteralPath $full -Recurse -Force -ErrorAction Stop;Write-Host "Removed $relative"}catch{Write-Warning "Kept ${relative}: $($_.Exception.Message)"}}}}

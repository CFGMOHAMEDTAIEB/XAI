param(
    [switch]$Json
)

# Configuration of tools to check
$tools = @(
    @{ Name = "node"; VersionCommand = "node --version" },
    @{ Name = "npm"; VersionCommand = "npm --version" },
    @{ Name = "python"; VersionCommand = "python --version" },
    @{ Name = "dotnet"; VersionCommand = "dotnet --version" },
    @{ Name = "git"; VersionCommand = "git --version" },
    @{ Name = "rustc"; VersionCommand = "rustc --version" },
    @{ Name = "cargo"; VersionCommand = "cargo --version" }
)

function Get-CommandVersion {
    param(
        [string]$CommandName,
        [string]$VersionCommand
    )

    $result = @{
        Tool = $CommandName
        Found = $false
        Path = $null
        Version = $null
        Error = $null
    }

    try {
        # 1. Use Get-Command first
        $commandInfo = Get-Command $CommandName -ErrorAction SilentlyContinue
        $commandPath = $null
        if ($commandInfo -and $commandInfo.Source) {
            $commandPath = $commandInfo.Source
        }

        # 2. Fallback to where.exe
        if (-not $commandPath) {
            $whereOutput = (where.exe $CommandName 2>$null | Select-Object -First 1).Trim()
            if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrEmpty($whereOutput)) {
                $commandPath = $whereOutput
            }
        }

        if ($commandPath -and (Test-Path $commandPath -PathType Leaf)) {
            $result.Path = $commandPath
            
            # 3. Execute the version command to be certain.
            $versionOutput = (Invoke-Expression $VersionCommand 2>&1 | Out-String).Trim()
            
            if ($LASTEXITCODE -eq 0) {
                $result.Found = $true
                $result.Version = $versionOutput.Split([System.Environment]::NewLine)[0].Trim()
            } else {
                $result.Error = "Found at '$commandPath', but version command failed: $versionOutput"
            }
        } else {
            $result.Error = "'$CommandName' not found via Get-Command or where.exe"
        }
    } catch {
        $result.Error = "An exception occurred while checking for '$CommandName': $($_.Exception.Message)"
    }

    return [pscustomobject]$result
}

$results = @()
$allFound = $true

foreach ($tool in $tools) {
    $status = Get-CommandVersion -CommandName $tool.Name -VersionCommand $tool.VersionCommand
    $results += $status
    if (-not $status.Found) {
        $allFound = $false
    }
}

if ($Json) {
    $results | ConvertTo-Json -Depth 3 | Write-Output
} else {
    $results | ForEach-Object {
        if ($_.Found) {
            Write-Host "[OK] $($_.Tool) found."
            Write-Host "   - Path: $($_.Path)"
            Write-Host "   - Version: $($_.Version)"
        } else {
            Write-Host "[MISSING] $($_.Tool) not found or version command failed."
            Write-Host "   - Details: $($_.Error)"
        }
    }
}

if (-not $allFound) {
    exit 1
}

exit 0
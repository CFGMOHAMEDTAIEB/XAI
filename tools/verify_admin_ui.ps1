param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^https?://(localhost|127\.0\.0\.1)(:\d+)?$')]
    [string]$BaseUrl
)

$ErrorActionPreference = 'Stop'
$login = Invoke-WebRequest -UseBasicParsing "$BaseUrl/login"
if ($login.StatusCode -ne 200) { throw "GET /login returned $($login.StatusCode)" }

$links = [regex]::Matches($login.Content, '<link[^>]+rel=["'']stylesheet["''][^>]+href=["'']([^"'']+)["'']', 'IgnoreCase')
if ($links.Count -eq 0) { throw 'Rendered HTML contains no stylesheet reference.' }

$requiredHtmlClasses = @('admin-auth-shell', 'admin-login-card', 'admin-login-form', 'form-field', 'password-input-wrap', 'password-toggle')
foreach ($className in $requiredHtmlClasses) {
    if (-not $login.Content.Contains($className)) { throw "Rendered login HTML is missing $className" }
}
if ($login.Content.Contains('app-shell')) { throw 'The authenticated admin shell rendered on /login.' }
if ($login.Content.Contains('XAI-CompressAdministrator console')) { throw 'Rendered HTML contains the concatenated legacy brand.' }
if ($login.Content.Contains('>Show</button>')) { throw 'Rendered HTML contains the plain Show button.' }

$stylesheets = foreach ($link in $links) {
    $href = $link.Groups[1].Value
    $uri = [Uri]::new([Uri]::new("$BaseUrl/"), $href)
    $response = Invoke-WebRequest -UseBasicParsing $uri.AbsoluteUri
    if ($response.StatusCode -ne 200) { throw "$href returned $($response.StatusCode)" }
    if ($response.Headers['Content-Type'] -notmatch '^text/css') { throw "$href returned MIME $($response.Headers['Content-Type'])" }
    if ([string]::IsNullOrWhiteSpace($response.Content)) { throw "$href returned empty CSS" }
    [pscustomobject]@{ Href = $href; Css = $response.Content }
}

$css = ($stylesheets.Css -join "`n")
$requiredSelectors = @('.admin-auth-shell', '.admin-login-card', '.admin-login-form', '.form-field', '.password-input-wrap', '.password-toggle', '.sidebar', '.topbar')
foreach ($selector in $requiredSelectors) {
    if (-not $css.Contains($selector)) { throw "Loaded CSS is missing $selector" }
}

$loginSource = Get-Content -Raw -LiteralPath (Join-Path $PSScriptRoot '../apps/admin_dotnet/Components/Pages/Login.razor')
$mainLayout = Get-Content -Raw -LiteralPath (Join-Path $PSScriptRoot '../apps/admin_dotnet/Components/Layout/MainLayout.razor')
if ($loginSource -notmatch '@layout AuthLayout') { throw 'Login does not use AuthLayout.' }
if ($loginSource -notmatch 'class="admin-login-form"') { throw 'Login form is missing its layout class.' }
if ($loginSource -match 'XAI-CompressAdministrator console') { throw 'Concatenated legacy brand text remains.' }
if ($loginSource -match '>Show</button>') { throw 'Plain Show password button remains.' }
if ($mainLayout -match 'login-shell') { throw 'MainLayout still owns the auth shell.' }

"ADMIN_UI_HTTP_TEST = PASS"
"LOGIN_STATUS = $($login.StatusCode)"
foreach ($sheet in $stylesheets) { "STYLESHEET = $($sheet.Href)" }

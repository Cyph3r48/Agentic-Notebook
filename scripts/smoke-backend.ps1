param(
    [string]$BaseUrl = "http://localhost:8000",
    [string]$Email = "admin@structuredintelligence.com",
    [string]$Password = "change_me_immediately"
)

$ErrorActionPreference = "Stop"

function Assert-Status {
    param(
        [int]$Actual,
        [int[]]$Allowed,
        [string]$Step
    )
    if ($Allowed -notcontains $Actual) {
        throw "$Step failed with HTTP $Actual"
    }
}

Write-Host "Checking /health..."
$health = Invoke-WebRequest -Uri "$BaseUrl/health" -Method GET
Assert-Status -Actual $health.StatusCode -Allowed @(200) -Step "/health"

Write-Host "Checking /ready..."
$ready = Invoke-WebRequest -Uri "$BaseUrl/ready" -Method GET
Assert-Status -Actual $ready.StatusCode -Allowed @(200, 503) -Step "/ready"

Write-Host "Logging in (/api/v1/auth/login)..."
$loginBody = @{
    email = $Email
    password = $Password
} | ConvertTo-Json

$login = Invoke-WebRequest -Uri "$BaseUrl/api/v1/auth/login" -Method POST -Body $loginBody -ContentType "application/json"
Assert-Status -Actual $login.StatusCode -Allowed @(200) -Step "/api/v1/auth/login"
$loginJson = $login.Content | ConvertFrom-Json

$accessToken = $loginJson.access_token
$refreshToken = $loginJson.refresh_token
if (-not $accessToken -or -not $refreshToken) {
    throw "Login response missing tokens"
}

$authHeaders = @{
    Authorization = "Bearer $accessToken"
}

Write-Host "Checking /api/v1/auth/me..."
$me = Invoke-WebRequest -Uri "$BaseUrl/api/v1/auth/me" -Method GET -Headers $authHeaders
Assert-Status -Actual $me.StatusCode -Allowed @(200) -Step "/api/v1/auth/me"

Write-Host "Refreshing token (/api/v1/auth/refresh)..."
$refreshBody = @{
    refresh_token = $refreshToken
} | ConvertTo-Json

$refresh = Invoke-WebRequest -Uri "$BaseUrl/api/v1/auth/refresh" -Method POST -Body $refreshBody -ContentType "application/json"
Assert-Status -Actual $refresh.StatusCode -Allowed @(200) -Step "/api/v1/auth/refresh"
$refreshJson = $refresh.Content | ConvertFrom-Json

Write-Host "Listing documents (/api/v1/documents)..."
$docsHeaders = @{
    Authorization = "Bearer $($refreshJson.access_token)"
}
$docs = Invoke-WebRequest -Uri "$BaseUrl/api/v1/documents" -Method GET -Headers $docsHeaders
Assert-Status -Actual $docs.StatusCode -Allowed @(200) -Step "/api/v1/documents"

Write-Host "Logging out (/api/v1/auth/logout)..."
$logoutBody = @{
    refresh_token = $refreshJson.refresh_token
} | ConvertTo-Json
$logout = Invoke-WebRequest -Uri "$BaseUrl/api/v1/auth/logout" -Method POST -Body $logoutBody -ContentType "application/json"
Assert-Status -Actual $logout.StatusCode -Allowed @(204) -Step "/api/v1/auth/logout"

Write-Host "Smoke checks passed."

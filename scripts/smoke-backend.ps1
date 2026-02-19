param(
    [string]$BaseUrl = "http://localhost:8000",
    [string]$Email = "admin@structuredintelligence.com",
    [string]$Password = "change_me_immediately"
)

$ErrorActionPreference = "Stop"

function Invoke-CurlJsonOrText {
    param(
        [string]$Method,
        [string]$Url,
        [hashtable]$Headers = @{},
        [string]$JsonBody = "",
        [int[]]$AllowedCurlExitCodes = @(0)
    )
    $args = @("-sS", "-X", $Method, $Url, "-w", "`n__STATUS__:%{http_code}")
    foreach ($entry in $Headers.GetEnumerator()) {
        $args += @("-H", "$($entry.Key): $($entry.Value)")
    }
    $tmpBodyPath = $null
    if (-not [string]::IsNullOrWhiteSpace($JsonBody)) {
        $tmpFile = New-TemporaryFile
        $tmpBodyPath = $tmpFile.FullName
        Set-Content -Path $tmpBodyPath -Value $JsonBody -Encoding utf8 -NoNewline
        $args += @("-H", "Content-Type: application/json", "--data-binary", "@$tmpBodyPath")
    }

    try {
        $raw = & curl.exe @args
    } finally {
        if ($null -ne $tmpBodyPath -and (Test-Path $tmpBodyPath)) {
            Remove-Item -Path $tmpBodyPath -Force
        }
    }
    if ($AllowedCurlExitCodes -notcontains $LASTEXITCODE) {
        throw "curl failed for $Method $Url (exit code $LASTEXITCODE)"
    }

    $lines = $raw -split "`n"
    if ($lines.Count -lt 1) {
        throw "curl returned empty response for $Method $Url"
    }
    $statusLine = $lines[-1]
    if ($statusLine -notmatch "^__STATUS__:(\d{3})$") {
        throw "Unable to parse HTTP status for $Method $Url"
    }
    $statusCode = [int]$Matches[1]
    $body = ($lines | Select-Object -SkipLast 1) -join "`n"
    return @{
        StatusCode = $statusCode
        Body = $body
    }
}

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
$health = Invoke-CurlJsonOrText -Method "GET" -Url "$BaseUrl/health"
Assert-Status -Actual $health.StatusCode -Allowed @(200) -Step "/health"

Write-Host "Checking /ready..."
$ready = Invoke-CurlJsonOrText -Method "GET" -Url "$BaseUrl/ready"
Assert-Status -Actual $ready.StatusCode -Allowed @(200, 503) -Step "/ready"

Write-Host "Logging in (/api/v1/auth/login)..."
$loginBody = @{
    email = $Email
    password = $Password
} | ConvertTo-Json

$login = Invoke-CurlJsonOrText -Method "POST" -Url "$BaseUrl/api/v1/auth/login" -JsonBody $loginBody
Assert-Status -Actual $login.StatusCode -Allowed @(200) -Step "/api/v1/auth/login"
$loginJson = $login.Body | ConvertFrom-Json

$accessToken = $loginJson.access_token
$refreshToken = $loginJson.refresh_token
if (-not $accessToken -or -not $refreshToken) {
    throw "Login response missing tokens"
}

$authHeaders = @{
    Authorization = "Bearer $accessToken"
}

Write-Host "Checking /api/v1/auth/me..."
$me = Invoke-CurlJsonOrText -Method "GET" -Url "$BaseUrl/api/v1/auth/me" -Headers $authHeaders
Assert-Status -Actual $me.StatusCode -Allowed @(200) -Step "/api/v1/auth/me"

Write-Host "Checking /api/v1/chat/models..."
$models = Invoke-CurlJsonOrText -Method "GET" -Url "$BaseUrl/api/v1/chat/models" -Headers $authHeaders
Assert-Status -Actual $models.StatusCode -Allowed @(200) -Step "/api/v1/chat/models"
$modelsJson = $models.Body | ConvertFrom-Json
if ($null -eq $modelsJson.ollama -or $null -eq $modelsJson.anthropic) {
    throw "/api/v1/chat/models response missing provider keys"
}

Write-Host "Checking /api/v1/chat/providers/health..."
$providerHealth = Invoke-CurlJsonOrText -Method "GET" -Url "$BaseUrl/api/v1/chat/providers/health" -Headers $authHeaders
Assert-Status -Actual $providerHealth.StatusCode -Allowed @(200) -Step "/api/v1/chat/providers/health"
$providerHealthJson = $providerHealth.Body | ConvertFrom-Json
if ($null -eq $providerHealthJson.ollama -or $null -eq $providerHealthJson.anthropic) {
    throw "/api/v1/chat/providers/health response missing provider keys"
}

Write-Host "Creating chat conversation (/api/v1/chat/conversations)..."
$conversationBody = @{
    title = "backend-smoke"
} | ConvertTo-Json
$conversation = Invoke-CurlJsonOrText -Method "POST" -Url "$BaseUrl/api/v1/chat/conversations" -Headers $authHeaders -JsonBody $conversationBody
Assert-Status -Actual $conversation.StatusCode -Allowed @(201) -Step "/api/v1/chat/conversations"
$conversationJson = $conversation.Body | ConvertFrom-Json
if (-not $conversationJson.id) {
    throw "Conversation response missing id"
}

Write-Host "Checking streamed chat events (/api/v1/chat/conversations/{id}/messages/stream)..."
$streamBody = @{
    content = "smoke stream check"
    use_rag = $false
} | ConvertTo-Json
$stream = Invoke-CurlJsonOrText -Method "POST" -Url "$BaseUrl/api/v1/chat/conversations/$($conversationJson.id)/messages/stream" -Headers $authHeaders -JsonBody $streamBody -AllowedCurlExitCodes @(0, 18)
Assert-Status -Actual $stream.StatusCode -Allowed @(200) -Step "/api/v1/chat/conversations/{id}/messages/stream"
if ($stream.Body -notmatch "event:") {
    throw "Stream response missing SSE events"
}

Write-Host "Refreshing token (/api/v1/auth/refresh)..."
$refreshBody = @{
    refresh_token = $refreshToken
} | ConvertTo-Json

$refresh = Invoke-CurlJsonOrText -Method "POST" -Url "$BaseUrl/api/v1/auth/refresh" -JsonBody $refreshBody
Assert-Status -Actual $refresh.StatusCode -Allowed @(200) -Step "/api/v1/auth/refresh"
$refreshJson = $refresh.Body | ConvertFrom-Json

Write-Host "Listing documents (/api/v1/documents)..."
$docsHeaders = @{
    Authorization = "Bearer $($refreshJson.access_token)"
}
$docs = Invoke-CurlJsonOrText -Method "GET" -Url "$BaseUrl/api/v1/documents" -Headers $docsHeaders
Assert-Status -Actual $docs.StatusCode -Allowed @(200) -Step "/api/v1/documents"

Write-Host "Logging out (/api/v1/auth/logout)..."
$logoutBody = @{
    refresh_token = $refreshJson.refresh_token
} | ConvertTo-Json
$logout = Invoke-CurlJsonOrText -Method "POST" -Url "$BaseUrl/api/v1/auth/logout" -JsonBody $logoutBody
Assert-Status -Actual $logout.StatusCode -Allowed @(204) -Step "/api/v1/auth/logout"

Write-Host "Smoke checks passed."

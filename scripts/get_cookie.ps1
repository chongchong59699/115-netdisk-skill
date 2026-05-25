param(
    [ValidateSet("web", "android", "ios", "linux", "mac", "windows", "tv", "alipaymini", "wechatmini", "qandroid")]
    [string]$App = "tv",

    [string]$CookiePath = "~/.115-cookies",

    [string]$QrPath = "",

    [switch]$NoSave,

    [switch]$PrintCookie,

    [switch]$NoOpen,

    [int]$PollIntervalSeconds = 2
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

function ConvertTo-QueryString {
    param([hashtable]$Values)
    ($Values.GetEnumerator() | ForEach-Object {
        "{0}={1}" -f [Uri]::EscapeDataString([string]$_.Key), [Uri]::EscapeDataString([string]$_.Value)
    }) -join "&"
}

function Get-ResponseData {
    param($Response, [string]$Action)
    if ($null -eq $Response -or $null -eq $Response.data) {
        throw "$Action 失败：接口响应中没有 data 字段。原始响应：$($Response | ConvertTo-Json -Depth 10 -Compress)"
    }
    return $Response.data
}

function Resolve-UserPath {
    param([string]$Path)
    if ($Path.StartsWith("~/") -or $Path.StartsWith("~\")) {
        return Join-Path $HOME $Path.Substring(2)
    }
    if ($Path -eq "~") {
        return $HOME
    }
    return $Path
}

function Resolve-AbsolutePath {
    param([string]$Path)
    $resolved = Resolve-UserPath $Path
    return [System.IO.Path]::GetFullPath($resolved)
}

function ConvertTo-FileUri {
    param([string]$Path)
    return ([System.Uri]::new($Path)).AbsoluteUri
}

function Write-QrMarkers {
    param([string]$ImagePath, [string]$RemoteUrl)
    $fileUri = ConvertTo-FileUri $ImagePath
    $markdownPath = $ImagePath.Replace("\", "/")
    $markdown = "![115 登录二维码]($markdownPath)"
    $payload = [ordered]@{
        type = "115-login-qr"
        image_path = $ImagePath
        image_uri = $fileUri
        remote_url = $RemoteUrl
        markdown = $markdown
        instruction = "请用 115 App 扫码，并在手机上确认登录。"
    } | ConvertTo-Json -Compress

    Write-Host "请用 115 App 扫码确认登录："
    Write-Host "QR_IMAGE_PATH: $ImagePath"
    Write-Host "QR_FILE_URI: $fileUri"
    Write-Host "QR_REMOTE_URL: $RemoteUrl"
    Write-Host "QR_MARKDOWN: $markdown"
    Write-Host "LOGIN_QR_JSON: $payload"
    Write-Host "如果 agent 没有成功展示图片，请手动打开该文件扫码：$ImagePath"
}

Write-Host "正在获取 115 登录二维码..."
$tokenResponse = Invoke-RestMethod -Method Get -Uri "https://qrcodeapi.115.com/api/1.0/web/1.0/token/"
$token = Get-ResponseData $tokenResponse "获取二维码 token"

$qrUrl = "https://qrcodeapi.115.com/api/1.0/mac/1.0/qrcode?uid=$([Uri]::EscapeDataString([string]$token.uid))"
$resolvedQrPath = if ($QrPath) {
    Resolve-AbsolutePath $QrPath
} else {
    Join-Path ([System.IO.Path]::GetTempPath()) "115-login-qrcode-$($token.uid).png"
}
$qrDir = Split-Path -Parent $resolvedQrPath
if ($qrDir) {
    New-Item -ItemType Directory -Force -Path $qrDir | Out-Null
}
Invoke-WebRequest -Method Get -Uri $qrUrl -OutFile $resolvedQrPath | Out-Null

Write-QrMarkers -ImagePath $resolvedQrPath -RemoteUrl $qrUrl
if (-not $NoOpen) {
    try {
        Start-Process $resolvedQrPath
    } catch {
        Write-Warning "打开二维码图片失败：$($_.Exception.Message)"
    }
}

$statusPayload = @{
    uid = $token.uid
    time = $token.time
    sign = $token.sign
}

while ($true) {
    Start-Sleep -Seconds $PollIntervalSeconds
    $statusUrl = "https://qrcodeapi.115.com/get/status/?" + (ConvertTo-QueryString $statusPayload)
    try {
        $statusResponse = Invoke-RestMethod -Method Get -Uri $statusUrl
    } catch {
        Write-Host "[status=?] 状态接口暂时无响应，继续等待扫码确认... ($($_.Exception.Message))"
        continue
    }
    $statusData = Get-ResponseData $statusResponse "获取二维码状态"
    $status = [int]$statusData.status

    switch ($status) {
        0 { Write-Host "[status=0] 等待扫码..." }
        1 { Write-Host "[status=1] 已扫码，请在手机上确认登录..." }
        2 {
            Write-Host "[status=2] 已确认登录。"
            break
        }
        -1 { throw "二维码已过期，请重新运行脚本。" }
        -2 { throw "用户已取消扫码登录。" }
        default {
            throw "二维码状态异常：$($statusResponse | ConvertTo-Json -Depth 10 -Compress)"
        }
    }

    if ($status -eq 2) {
        break
    }
}

$loginPayload = @{
    app = $App
    account = $token.uid
}
$loginUrl = "https://passportapi.115.com/app/1.0/$App/1.0/login/qrcode/"
$loginResponse = Invoke-RestMethod `
    -Method Post `
    -Uri $loginUrl `
    -ContentType "application/x-www-form-urlencoded" `
    -Body (ConvertTo-QueryString $loginPayload)

$loginData = Get-ResponseData $loginResponse "获取登录结果"
if ($null -eq $loginData.cookie) {
    throw "登录结果中没有 cookie 字段，可能是 app 类型不可用。原始响应：$($loginResponse | ConvertTo-Json -Depth 10 -Compress)"
}

$cookieText = ($loginData.cookie.PSObject.Properties | ForEach-Object {
    "{0}={1}" -f $_.Name, $_.Value
}) -join "; "

if (-not $NoSave) {
    $resolvedCookiePath = Resolve-AbsolutePath $CookiePath
    $cookieDir = Split-Path -Parent $resolvedCookiePath
    if ($cookieDir) {
        New-Item -ItemType Directory -Force -Path $cookieDir | Out-Null
    }
    $utf8NoBom = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllText($resolvedCookiePath, $cookieText, $utf8NoBom)
    Write-Host "Cookies 已保存到：$resolvedCookiePath"
}

if ($PrintCookie -or $NoSave) {
    Write-Output $cookieText
}

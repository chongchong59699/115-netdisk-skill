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

Write-Host "请用 115 App 扫码确认登录："
Write-Host "二维码图片已保存到：$resolvedQrPath"
Write-Host "如果 agent 发送图片失败，请打开上面的文件扫码。"
Write-Host $qrUrl
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
    $statusResponse = Invoke-RestMethod -Method Get -Uri $statusUrl
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

---
name: 115-netdisk
description: 115 网盘集成，支持 115扫码登录/115扫码登陆、二维码图片交互获取 cookies、cookies 保存与验证、目录浏览、文件搜索、离线下载任务添加和任务查询。使用 p115client SDK，基于 cookies 认证。Use when the user asks about 115网盘, 115云盘, 115扫码登录, 115扫码登陆, 115离线下载, p115client, 115 pan, or 115 netdisk operations.
---

# 115 网盘集成

## 安装本 Skill

当用户给出本仓库的 `SKILL.md` 或 `install.py` 远程 URL 并要求安装时，必须安装完整 skill 文件集，而不是只保存这个 `SKILL.md` 文件，因为脚本都在 `scripts/` 中。本仓库采用“仓库根目录即 skill 根目录”的结构，关键文件包括 `SKILL.md`、`scripts/`、`agents/` 和 `requirements.txt`。

## Agent 兼容约定

本 skill 需要兼容 Codex、OpenClaw、Hermes 和普通 CLI 类 agent。扫码登录脚本不会假设某个平台一定能渲染 Markdown 图片，而是同时输出多种稳定标记：

- `LOGIN_QR_JSON`：紧凑 JSON，包含 `image_path`、`image_uri`、`remote_url`、`markdown`。
- `QR_IMAGE_PATH`：二维码 PNG 本地路径，适合能上传/展示本地图片的 agent。
- `QR_FILE_URI`：`file://` URI，适合能打开本地文件 URI 的 agent。
- `QR_REMOTE_URL`：115 二维码远程图片 URL，适合纯 CLI 或无法读取本地图片的 agent。
- `QR_MARKDOWN`：Markdown 图片语法，适合聊天界面支持本地图片渲染的 agent。

所有 agent 在运行 `scripts/login.py --no-open` 或 release 二进制后，应监听 stdout；一旦看到上述任意二维码标记，就立即用自己支持的方式展示、打开或转述给用户，并保持进程继续运行等待用户扫码确认。单纯在 shell 输出里打印 `QR_MARKDOWN` 不等于已经把图片展示给用户。

推荐安装方式：使用 `curl` 获取仓库根目录的 `install.py`，让安装器下载 GitHub zip 包并复制完整 skill。安装器自身只依赖 Python 标准库，不依赖 git，Windows / macOS / Linux 都可用；安装完成后如果能找到 Python 3.12+，会自动执行 `pip install -r requirements.txt` 安装 `p115client`。

```bash
curl -fsSL https://raw.githubusercontent.com/chongchong59699/115-netdisk-skill/master/install.py | python - --repo chongchong59699/115-netdisk-skill --branch master
```

Windows 如果 `python` 命令不可用，优先尝试：

```powershell
curl.exe -fsSL https://raw.githubusercontent.com/chongchong59699/115-netdisk-skill/master/install.py | py - --repo chongchong59699/115-netdisk-skill --branch master
```

如果用户只想复制 skill 文件、跳过依赖安装，可给安装器追加 `--no-deps`。

如果用户只提供了 GitHub 上的 `SKILL.md` URL，也可以把 URL 传给安装器，安装器会反推出仓库和分支：

```bash
curl -fsSL https://raw.githubusercontent.com/chongchong59699/115-netdisk-skill/master/install.py | python - --skill-url https://raw.githubusercontent.com/chongchong59699/115-netdisk-skill/master/SKILL.md
```

如果用户提供的是 `curl -fsSL https://.../SKILL.md` 这类自定义域名，先读取该 `SKILL.md` 正文；若正文没有给出 GitHub 仓库或安装器 URL，先询问仓库地址。

安装流程：

1. 优先使用上面的 `install.py` 一行安装。
2. 如果只能手工安装，从用户提供的 URL 推导 GitHub 仓库地址。常见格式：
   - `https://raw.githubusercontent.com/<chongchong59699>/<REPO>/<BRANCH>/SKILL.md`
   - `https://github.com/<chongchong59699>/<REPO>/blob/<BRANCH>/SKILL.md`
   - 兼容旧结构：`https://raw.githubusercontent.com/<chongchong59699>/<REPO>/<BRANCH>/115-netdisk/SKILL.md`
   - 如果仓库 URL 无法从用户请求或 `SKILL.md` URL 推导出来，先向用户询问仓库地址，不要只安装单个 `SKILL.md` 文件。
3. 将仓库根目录中的 skill 文件集复制到 Codex skills 目录：
   - 优先使用 `$CODEX_HOME/skills`
   - 未设置时使用 `~/.codex/skills`
   - 最终目录应为 `~/.codex/skills/115-netdisk/SKILL.md`
4. 安装器会自动寻找 Python 3.12+ 并安装 `requirements.txt`；扫码登录脚本 `scripts/login.py` 只依赖 Python 标准库，不要求 Python 3.12。如果未找到 Python 3.12+，安装器会跳过依赖安装并给出明确提示。
5. 安装后枚举运行 `python -m py_compile scripts/*.py` 验证 Python 脚本语法；仅在 Windows/PowerShell 可用时检查 `scripts/get_cookie.ps1`。如果当前 Python 低于 3.12，只需告知用户网盘功能脚本需要 Python 3.12+，扫码登录仍可用。

PowerShell 7 示例，替换 `chongchong59699`、`REPO`、`BRANCH` 后执行：

```powershell
$owner = "chongchong59699"
$repo = "REPO"
$branch = "master"
$targetRoot = if ($env:CODEX_HOME) { Join-Path $env:CODEX_HOME "skills" } else { Join-Path $HOME ".codex\skills" }
$tmp = Join-Path ([System.IO.Path]::GetTempPath()) "115-netdisk-skill-$([guid]::NewGuid())"
git clone --depth 1 --branch $branch "https://github.com/$owner/$repo.git" $tmp
New-Item -ItemType Directory -Force -Path $targetRoot | Out-Null
$targetSkill = Join-Path $targetRoot "115-netdisk"
if (Test-Path -LiteralPath $targetSkill) { Remove-Item -LiteralPath $targetSkill -Recurse -Force }
New-Item -ItemType Directory -Force -Path $targetSkill | Out-Null
Copy-Item -LiteralPath (Join-Path $tmp "SKILL.md") -Destination $targetSkill -Force
Copy-Item -LiteralPath (Join-Path $tmp "requirements.txt") -Destination $targetSkill -Force
Copy-Item -LiteralPath (Join-Path $tmp "agents") -Destination $targetSkill -Recurse -Force
Copy-Item -LiteralPath (Join-Path $tmp "scripts") -Destination $targetSkill -Recurse -Force
Remove-Item -LiteralPath $tmp -Recurse -Force
```

POSIX shell 示例，替换 `chongchong59699`、`REPO`、`BRANCH` 后执行：

```bash
owner="chongchong59699"
repo="REPO"
branch="master"
target_root="${CODEX_HOME:-$HOME/.codex}/skills"
tmp="$(mktemp -d)"
git clone --depth 1 --branch "$branch" "https://github.com/$owner/$repo.git" "$tmp"
mkdir -p "$target_root"
rm -rf "$target_root/115-netdisk"
mkdir -p "$target_root/115-netdisk"
cp "$tmp/SKILL.md" "$tmp/requirements.txt" "$target_root/115-netdisk/"
cp -R "$tmp/agents" "$tmp/scripts" "$target_root/115-netdisk/"
rm -rf "$tmp"
```

## 快速开始

默认 cookies 路径为 `~/.115-cookies`。当目录浏览、搜索、离线下载等脚本发现该文件不存在或内容为空时，会自动提醒用户扫码登录、生成 115 登录二维码 PNG、等待用户用 115 App 扫码确认，并把 cookies 保存到 `~/.115-cookies`。

agent 看到脚本输出 `LOGIN_QR_JSON: ...`、`QR_IMAGE_PATH: ...`、`QR_FILE_URI: ...`、`QR_REMOTE_URL: ...` 或 `QR_MARKDOWN: ...` 后，应立即把二维码图片发给用户；Codex、OpenClaw、Hermes 或 CLI agent 都不应假设 shell 输出中的 Markdown 会自动弹图，必须由 agent 在普通回复中展示、打开或转述图片目标。如果图片发送失败，提醒用户打开该本地路径或远程 URL 扫码。扫码登录成功后，脚本会默认输出用户基本信息和本 skill 支持的功能点。

### 第一步：获取 Cookies

用户提供的 cookies 格式（4 个字段缺一不可）：
```
UID=xxx; CID=xxx; SEID=xxx; KID=xxx
```

跨平台默认方案：使用纯 Python 标准库登录脚本。agent 应优先运行这个命令，因为它在 Windows / macOS / Linux 上都可用，不依赖 PowerShell，也不依赖 `p115client`：

```bash
python scripts/login.py --no-open
```

如果当前系统只有 `python3` 或 Windows `py` launcher，则改用：

```bash
python3 scripts/login.py --no-open
py -3 scripts/login.py --no-open
```

脚本会把二维码保存为本地 PNG、输出 `LOGIN_QR_JSON`、`QR_IMAGE_PATH`、`QR_FILE_URI`、`QR_REMOTE_URL` 和 `QR_MARKDOWN`，并继续轮询扫码状态。agent 应把二维码图片发给用户；如果图片没有成功显示，必须提醒用户打开脚本输出的二维码文件路径或远程 URL 自行扫码。用户用 115 App 扫码并确认后，脚本会自动获取 cookies 并默认保存到 `~/.115-cookies`。状态接口偶发 read timeout 时脚本会继续等待，不会立即退出。

可选参数：

```bash
# 指定二维码图片保存位置
python scripts/login.py --qr-path /tmp/115-login-qrcode.png --no-open

# 指定 cookies 保存位置
python scripts/login.py --cookie-path ~/.115-cookies --no-open

# 指定 app 类型，默认 tv
python scripts/login.py --app web --no-open
```

免 Python 方案：使用 GitHub Releases 中的 `115-cookie-helper-*` 独立二进制。它是跨平台的，但需要下载与当前系统/架构匹配的文件。

macOS：

```bash
# Apple Silicon
chmod +x ./115-cookie-helper-darwin-arm64
./115-cookie-helper-darwin-arm64

# Intel Mac
chmod +x ./115-cookie-helper-darwin-amd64
./115-cookie-helper-darwin-amd64
```

如果 macOS 提示无法验证开发者，先在“系统设置 → 隐私与安全性”中允许运行，或执行：

```bash
xattr -d com.apple.quarantine ./115-cookie-helper-darwin-arm64
```

Windows：

```powershell
.\115-cookie-helper-windows-amd64.exe
```

Linux：

```bash
chmod +x ./115-cookie-helper-linux-amd64
./115-cookie-helper-linux-amd64
```

Windows 备用方案：如果用户没有合适的 Python 或 release 二进制，可用 PowerShell 脚本获取并保存 cookies。不要在 macOS/Linux 上把它作为默认路径：

```powershell
pwsh -ExecutionPolicy Bypass -File scripts/get_cookie.ps1 -NoOpen
```

PowerShell 脚本会把二维码保存为本地 PNG 并输出绝对路径，然后继续轮询扫码状态。agent 应在看到 `二维码图片已保存到：...` 后立刻把图片发给用户，例如：

```markdown
![115 登录二维码](C:\Users\...\AppData\Local\Temp\115-login-qrcode-xxx.png)
```

如果图片没有成功显示，必须提醒用户打开脚本输出的二维码文件路径自行扫码。用户用 115 App 扫码并确认后，脚本会自动获取 cookies 并默认保存到 `~/.115-cookies`。

可选参数：

```powershell
# 指定二维码图片保存位置
pwsh -ExecutionPolicy Bypass -File scripts/get_cookie.ps1 -QrPath "D:\115-login-qrcode.png" -NoOpen

# 允许脚本自动打开二维码图片
pwsh -ExecutionPolicy Bypass -File scripts/get_cookie.ps1

# 只打印 cookies，不保存
pwsh -ExecutionPolicy Bypass -File scripts/get_cookie.ps1 -NoSave

# 保存到指定路径
pwsh -ExecutionPolicy Bypass -File scripts/get_cookie.ps1 -CookiePath "D:\115-cookies.txt"

# 指定 app 类型，默认 tv
pwsh -ExecutionPolicy Bypass -File scripts/get_cookie.ps1 -App web
```

GitHub Releases 中的 `115-cookie-helper-*` 独立二进制也支持同样的二维码文件交互：

```powershell
.\115-cookie-helper-windows-amd64.exe -no-open
.\115-cookie-helper-windows-amd64.exe -qr-path "D:\115-login-qrcode.png" -no-open
```

备用方案，如果用户已经手动拿到了 cookies，则保存并验证：

运行保存脚本（自动持久化到 `~/.115-cookies`）：

```bash
printf '%s' 'UID=xxx; CID=xxx; SEID=xxx; KID=xxx' | python3 scripts/save_cookies.py --stdin
```

或使用环境变量 / 交互式运行：
```bash
P115_COOKIES='UID=xxx; CID=xxx; SEID=xxx; KID=xxx' python3 scripts/save_cookies.py --env
python3 scripts/save_cookies.py
```

不推荐把 cookies 直接作为命令行参数传入，因为可能进入 shell 历史或进程列表。

### 第二步：测试连接

```bash
python3 scripts/test_connection.py
```

输出用户信息、存储空间、根目录预览即表示连接正常。

### 第三步：使用功能

```bash
# 浏览目录
python3 scripts/browse.py [目录ID]

# 添加离线下载
python3 scripts/offline_download.py 'magnet:?xt=urn:btih:xxx'

# 查看离线任务
python3 scripts/offline_download.py --list
```

## 安装依赖

p115client 当前要求 Python 3.12+：

```bash
python3.12 -m pip install p115client
# 或指定 Python 路径
uv pip install --python /path/to/python3.12 p115client
```

## Cookies 持久化说明

- **标准路径：** `~/.115-cookies`（即 `/root/.115-cookies` 或 `/home/<user>/.115-cookies`）
- **格式：** 纯文本，单行，格式为 `UID=xxx; CID=xxx; SEID=xxx; KID=xxx`
- **权限：** 建议 `chmod 600` 仅本人可读写
- **过期：** Cookies 有有效期，过期后需用户重新从浏览器获取。脚本用 `Path` 对象初始化 `P115Client(..., check_for_relogin=True)`，如果 SDK 自动续期成功，会尝试写回 cookies 文件。
- **读取方式：** 普通字符串会被 p115client 当作 cookies 内容解析；如果要传文件路径，必须传 `pathlib.Path`/`os.PathLike`，或者先 `open().read()` 读取内容。

## ⚠️ 关键 Pitfalls

### 1. 不能把普通字符串路径传给 P115Client

```python
# ❌ 报错 ValueError: dictionary update sequence element #0 has length 1; 2 is required
client = P115Client("/path/to/cookies.txt")

# ✅ 正确：用 PathLike，续期后可写回文件
from pathlib import Path
client = P115Client(Path("/path/to/cookies.txt"), check_for_relogin=True)

# ✅ 也可以读取文件内容，但续期后的 cookies 不会自动写回这个文件
with open("/path/to/cookies.txt") as f:
    cookies = f.read().strip()
client = P115Client(cookies, check_for_relogin=True)
```

### 2. API 字段名是缩写

| 字段 | 含义 | 常见错误 |
|------|------|----------|
| `n` | 文件/文件夹名 | ❌ `name` |
| `s` | 文件大小 (bytes) | ❌ `size` |
| `cid` | 目录 ID | ❌ `folder_id` |
| `fc` | 子项数量 | ❌ `count` |
| `pid` | 父目录 ID | ❌ `parent_id` |
| `pc` | pick code (下载用) | ❌ `pick_code` |
| `t` | 修改时间 (unix) | ❌ `mtime` |

### 3. Web API 在服务器上返回 405

`fs_files()` 从服务器 IP 调用会被拦截。**必须用 `fs_files_aps()`**，参数相同：

```python
# ❌ 服务器上会 405
result = client.fs_files({"cid": dir_id, "limit": 100})

# ✅ 用这个
result = client.fs_files_aps({"cid": dir_id, "limit": 100})
```

### 4. 响应结构

```python
{
    "state": true,
    "data": [  # 直接是列表
        {"cid": "xxx", "n": "文件夹名", "fc": 5, ...},   # 有 cid = 文件夹
        {"fid": "xxx", "n": "文件名", "s": 1048576, ...}  # 有 fid = 文件
    ]
}
```

## 常用 API 速查

```python
from p115client import P115Client

# 初始化
with open(os.path.expanduser("~/.115-cookies")) as f:
    client = P115Client(f.read().strip(), check_for_relogin=True)

# 用户信息
info = client.user_info()  # info['data']['user_name'], info['data']['is_vip']

# 存储空间
space = client.fs_storage_info()  # {type_id: {total, used}, ...}

# 浏览目录
items = client.fs_files_aps({"cid": 0, "limit": 100})['data']

# 搜索文件
result = client.fs_search({"search_value": "关键词", "limit": 50})

# 获取下载链接
url = client.download_url({"pick_code": "xxx"})

# 离线下载（磁力/ed2k/HTTP）
client.offline_add_url({"url": "magnet:?xt=urn:btih:xxx"})

# 指定保存相对目录用 savepath；指定目录 ID 用 wp_path_id
client.offline_add_url({"url": "https://example.com/file.zip", "savepath": "downloads"})

# 离线任务列表
tasks = client.offline_list()  # tasks['quota'], tasks['tasks']

# 离线配额
quota = client.offline_quota_info()  # quota['quota'], quota['total']

# 创建文件夹
client.fs_mkdir({"cname": "新文件夹", "pid": 0})

# 删除文件
client.fs_delete({"file_id": "xxx"})
```

## 相关资源

- p115client 文档: https://p115client.readthedocs.io/
- GitHub: https://github.com/ChenyangGao/p115client
- 115 开放平台: https://open.115.com/

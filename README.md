# 115 Netdisk Skill

给 Codex / AI agent 使用的 115 网盘 skill，支持 115 App 扫码登录、cookies 保存与验证、目录浏览、文件搜索、添加离线下载任务和查看任务状态。

本仓库按 skill 仓库组织：仓库根目录就是 skill 根目录。agent 安装时需要复制 `SKILL.md`、`scripts/`、`agents/` 和 `requirements.txt`，不要只保存单个 `SKILL.md`。

## AI 智能体安装

你可以把下面这行发给 AI 智能体，让它先读取 `SKILL.md` 中的安装说明：

```bash
curl -fsSL https://raw.githubusercontent.com/chongchong59699/115-netdisk-skill/master/SKILL.md
```


如果希望 agent 直接自动安装，使用下面这一行。安装器自身只依赖 Python 标准库，不依赖 git，会把完整 skill 安装到目标用户的 skills 目录；随后会在 skill 目录内创建私有 `.venv` 并安装 `p115client`。如果目标用户环境没有 Python 3.12+，安装器会尝试先安装/使用 `uv` 拉起 Python 3.12 环境，不要求用户手工装到系统 Python。

```bash
curl -fsSL https://raw.githubusercontent.com/chongchong59699/115-netdisk-skill/master/install.py | python - --repo chongchong59699/115-netdisk-skill --branch master
```

Windows 如果 `python` 不在 PATH，可尝试：

```powershell
curl.exe -fsSL https://raw.githubusercontent.com/chongchong59699/115-netdisk-skill/master/install.py | py - --repo chongchong59699/115-netdisk-skill --branch master
```

默认安装位置为 `${CODEX_HOME}/skills/115-netdisk` 或 `~/.codex/skills/115-netdisk`。

如需只复制 skill 文件、不安装 Python 依赖，可加 `--no-deps`，但这会让浏览目录、搜索、离线下载等功能在首次使用时缺少 `p115client`：

```bash
curl -fsSL https://raw.githubusercontent.com/chongchong59699/115-netdisk-skill/master/install.py | python - --repo chongchong59699/115-netdisk-skill --branch master --no-deps
```

## 手动安装

```bash
git clone https://github.com/chongchong59699/115-netdisk-skill.git
target_skill="${CODEX_HOME:-$HOME/.codex}/skills/115-netdisk"
rm -rf "$target_skill"
mkdir -p "$target_skill"
cp 115-netdisk-skill/SKILL.md 115-netdisk-skill/requirements.txt "$target_skill/"
cp -R 115-netdisk-skill/agents 115-netdisk-skill/scripts "$target_skill/"
```

Windows PowerShell 7：

```powershell
git clone https://github.com/chongchong59699/115-netdisk-skill.git
$targetSkill = if ($env:CODEX_HOME) { Join-Path $env:CODEX_HOME "skills\115-netdisk" } else { Join-Path $HOME ".codex\skills\115-netdisk" }
if (Test-Path -LiteralPath $targetSkill) { Remove-Item -LiteralPath $targetSkill -Recurse -Force }
New-Item -ItemType Directory -Force -Path $targetSkill | Out-Null
Copy-Item -LiteralPath ".\115-netdisk-skill\SKILL.md" -Destination $targetSkill -Force
Copy-Item -LiteralPath ".\115-netdisk-skill\requirements.txt" -Destination $targetSkill -Force
Copy-Item -LiteralPath ".\115-netdisk-skill\agents" -Destination $targetSkill -Recurse -Force
Copy-Item -LiteralPath ".\115-netdisk-skill\scripts" -Destination $targetSkill -Recurse -Force
```

## 运行要求

- 扫码登录：默认使用 `scripts/login.py --no-open`，只依赖 Python 标准库，Windows / macOS / Linux 都可用。
- 115 网盘功能：需要 Python 3.12+ 和 `p115client`；标准安装器会自动创建 `115-netdisk/.venv` 并安装。
- Windows 备用扫码登录：`scripts/get_cookie.ps1`，需要 PowerShell 7。
- 免 Python 备用方案：GitHub Releases 中的 `115-cookie-helper-*` 独立二进制。

手工安装 Python 依赖必须使用 Python 3.12+：

```bash
python3.12 -m pip install p115client
```

正常不需要手工执行上面的命令。安装器创建 `.venv` 后，`scripts/browse.py`、`scripts/test_connection.py`、`scripts/offline_download.py` 会自动切换到该私有 Python 环境运行。

## Agent 兼容

扫码登录需要兼容 Codex、OpenClaw、Hermes 和普通 CLI 类 agent。脚本和 release 二进制会同时输出这些二维码标记，agent 应监听 stdout 并选择自己支持的方式展示给用户：

- `LOGIN_QR_JSON`：包含 `image_path`、`image_uri`、`remote_url`、`markdown` 的 JSON。
- `QR_IMAGE_PATH`：本地 PNG 路径。
- `QR_FILE_URI`：本地 `file://` URI。
- `QR_REMOTE_URL`：115 二维码远程图片 URL。
- `QR_MARKDOWN`：Markdown 图片语法。

纯 CLI agent 至少应把 `QR_IMAGE_PATH` 或 `QR_REMOTE_URL` 原样告诉用户；支持图片附件的 agent 应直接展示 `QR_IMAGE_PATH` 指向的 PNG。shell 输出中出现 `QR_MARKDOWN` 不代表图片已经自动展示。

## 使用方式

在安装后的 skill 目录中运行：

```bash
python scripts/login.py --no-open
python scripts/test_connection.py
python scripts/browse.py
python scripts/browse.py --search 关键词
python scripts/offline_download.py 'magnet:?xt=urn:btih:xxx'
python scripts/offline_download.py --list
```

登录脚本会保存二维码 PNG，并输出 `LOGIN_QR_JSON`、`QR_IMAGE_PATH`、`QR_FILE_URI`、`QR_REMOTE_URL` 与 `QR_MARKDOWN`。Codex、OpenClaw、Hermes 或 CLI agent 需要读取这些标记后，把对应图片作为普通回复发给用户，或者提示用户打开路径/URL 自行扫码。cookies 默认保存到 `~/.115-cookies`。

## 发布二进制

仓库包含 GitHub Actions 工作流 `.github/workflows/release.yml`。推送 tag 后会自动构建 cookies 获取器：

```bash
git tag v0.1.0
git push origin v0.1.0
```

Release 产物包括 Windows、macOS 和 Linux 的独立二进制。

## 目录结构

```text
.
├── SKILL.md
├── agents/
│   ├── README.md
│   └── openai.yaml
├── scripts/
│   ├── browse.py
│   ├── get_cookie.ps1
│   ├── lib.py
│   ├── login.py
│   ├── offline_download.py
│   ├── save_cookies.py
│   └── test_connection.py
├── requirements.txt
├── install.py
├── cmd/
│   └── 115-cookie-helper/
│       └── master.go
└── .github/
    └── workflows/
        └── release.yml
```

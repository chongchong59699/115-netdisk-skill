# Agent compatibility notes

This skill is designed to work with Codex, OpenClaw, Hermes, and plain CLI-style agents.

When a login helper starts, it writes multiple machine-readable QR markers. Agents should watch stdout and use the first marker they support:

- `LOGIN_QR_JSON`: compact JSON payload with `image_path`, `image_uri`, `remote_url`, and `markdown`.
- `QR_IMAGE_PATH`: local PNG path. Best for agents that can attach or render local files.
- `QR_FILE_URI`: `file://` URI for agents or terminals that can open local files.
- `QR_REMOTE_URL`: remote 115 QR image URL. Best fallback for headless CLI agents.
- `QR_MARKDOWN`: Markdown image syntax for chat surfaces that render images from local paths.

Recommended behavior:

1. Start `scripts/login.py --no-open`.
2. As soon as a QR marker appears, show the QR image to the user or tell them exactly which path or URL to open.
3. Keep the process running while the user scans and confirms in the 115 App.
4. Treat transient `[status=?]` messages as network retries, not login failure.

Plain shell output containing `QR_MARKDOWN` is not enough by itself; the agent must actively render, attach, open, or relay the QR target.

Installers should run the repository `install.py`, not copy only `SKILL.md`. The installer creates a skill-local `.venv` and installs `p115client` there; feature scripts automatically switch into that environment when it exists.

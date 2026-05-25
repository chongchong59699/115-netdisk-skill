#!/usr/bin/env python3
"""
Install the 115-netdisk Codex skill from a GitHub repository or local checkout.

This installer intentionally uses only the Python standard library so agents can
bootstrap the skill with curl plus the system Python, without git.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
from typing import Optional, Tuple


SKILL_NAME = "115-netdisk"
SKILL_MARKERS = (f"{SKILL_NAME}/SKILL.md", "SKILL.md")
SKILL_FILE_NAMES = {"SKILL.md", "requirements.txt"}
SKILL_DIR_NAMES = {"agents", "assets", "references", "scripts"}
MIN_DEPENDENCY_PYTHON = (3, 12)
VENV_DIR_NAME = ".venv"


def fail(message: str, code: int = 1) -> None:
    print(f"Error: {message}", file=sys.stderr)
    raise SystemExit(code)


def find_skill_marker(path_tail: str, url: str) -> Tuple[str, int]:
    """Return the matching skill marker and its index in a GitHub path tail."""
    for marker in SKILL_MARKERS:
        marker_index = path_tail.rfind(marker)
        if marker_index >= 0 and path_tail.endswith(marker):
            return marker, marker_index
    fail(f"URL does not point at a supported SKILL.md location: {url}")


def parse_github_skill_url(url: str) -> Tuple[str, str, str]:
    """Return owner, repo, ref from a raw/blob URL pointing at SKILL.md."""
    parsed = urllib.parse.urlparse(url)
    parts = [part for part in parsed.path.split("/") if part]

    if parsed.netloc == "raw.githubusercontent.com":
        if len(parts) < 4:
            fail(f"cannot parse GitHub raw URL: {url}")
        owner, repo = parts[0], parts[1]
        tail = "/".join(parts[2:])
        _, marker_index = find_skill_marker(tail, url)
        ref = tail[:marker_index].rstrip("/")
        return owner, repo, ref

    if parsed.netloc in {"github.com", "www.github.com"}:
        if len(parts) < 5 or parts[2] not in {"blob", "tree"}:
            fail(f"cannot parse GitHub URL: {url}")
        owner, repo = parts[0], parts[1]
        tail = "/".join(parts[3:])
        _, marker_index = find_skill_marker(tail, url)
        ref = tail[:marker_index].rstrip("/")
        return owner, repo, ref

    fail(f"unsupported URL host: {parsed.netloc}")


def remove_git_suffix(value: str) -> str:
    return value[:-4] if value.endswith(".git") else value


def parse_repo(value: str) -> Tuple[str, str]:
    value = value.strip().rstrip("/")
    if value.startswith("http://") or value.startswith("https://"):
        parsed = urllib.parse.urlparse(value)
        parts = [part for part in parsed.path.split("/") if part]
        if parsed.netloc not in {"github.com", "www.github.com"} or len(parts) < 2:
            fail(f"--repo must be OWNER/REPO or a GitHub repo URL: {value}")
        return parts[0], remove_git_suffix(parts[1])
    parts = value.split("/")
    if len(parts) != 2 or not all(parts):
        fail(f"--repo must use OWNER/REPO format: {value}")
    return parts[0], remove_git_suffix(parts[1])


def default_target_root() -> Path:
    codex_home = os.environ.get("CODEX_HOME")
    if codex_home:
        return Path(codex_home).expanduser() / "skills"
    return Path.home() / ".codex" / "skills"


def download_archive(owner: str, repo: str, ref: str, archive_url: Optional[str]) -> bytes:
    if not archive_url:
        ref_path = "refs/heads/" + ref
        quoted = urllib.parse.quote(ref_path, safe="/")
        archive_url = f"https://codeload.github.com/{owner}/{repo}/zip/{quoted}"

    print(f"Downloading skill archive: {archive_url}")
    request = urllib.request.Request(
        archive_url,
        headers={"User-Agent": "115-netdisk-skill-installer/1.0"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def copy_tree(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def should_include_skill_path(rel_path: PurePosixPath) -> bool:
    if rel_path.is_absolute() or ".." in rel_path.parts or not rel_path.parts:
        return False
    if len(rel_path.parts) == 1:
        return rel_path.parts[0] in SKILL_FILE_NAMES
    return rel_path.parts[0] in SKILL_DIR_NAMES


def copy_skill_payload(src_root: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True, exist_ok=True)

    for name in sorted(SKILL_FILE_NAMES):
        src = src_root / name
        if src.exists():
            shutil.copy2(src, dst / name)

    for name in sorted(SKILL_DIR_NAMES):
        src = src_root / name
        if src.exists():
            copy_tree(src, dst / name)


def stage_from_source_dir(source_dir: Path, staging: Path) -> None:
    source_dir = source_dir.expanduser().resolve()
    if (source_dir / "SKILL.md").exists():
        skill_dir = source_dir
    elif (source_dir / SKILL_NAME / "SKILL.md").exists():
        skill_dir = source_dir / SKILL_NAME
    else:
        markers = " or ".join(SKILL_MARKERS)
        fail(f"could not find {markers} under {source_dir}")
    copy_skill_payload(skill_dir, staging / SKILL_NAME)


def stage_from_zip(archive: bytes, staging: Path) -> None:
    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
        tmp.write(archive)
        zip_path = Path(tmp.name)

    try:
        with zipfile.ZipFile(zip_path) as zf:
            marker_name = None
            for marker in SKILL_MARKERS:
                for name in zf.namelist():
                    normalized = name.replace("\\", "/")
                    if normalized.endswith(marker):
                        marker_name = normalized
                        break
                if marker_name:
                    break
            if not marker_name:
                markers = " or ".join(SKILL_MARKERS)
                fail(f"archive does not contain {markers}")

            prefix = marker_name[: -len("SKILL.md")]
            target_skill = staging / SKILL_NAME
            target_skill.mkdir(parents=True, exist_ok=True)

            for info in zf.infolist():
                name = info.filename.replace("\\", "/")
                if not name.startswith(prefix) or name == prefix:
                    continue
                rel = name[len(prefix) :]
                rel_path = PurePosixPath(rel)
                if rel_path.is_absolute() or ".." in rel_path.parts:
                    fail(f"unsafe archive path: {name}")
                if not should_include_skill_path(rel_path):
                    continue
                target_path = target_skill.joinpath(*rel_path.parts)
                if info.is_dir():
                    target_path.mkdir(parents=True, exist_ok=True)
                    continue
                target_path.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info) as src, target_path.open("wb") as dst:
                    shutil.copyfileobj(src, dst)
    finally:
        try:
            zip_path.unlink()
        except OSError:
            pass


def verify_install(skill_dir: Path) -> None:
    required = [
        skill_dir / "SKILL.md",
        skill_dir / "scripts" / "lib.py",
        skill_dir / "scripts" / "login.py",
        skill_dir / "scripts" / "browse.py",
        skill_dir / "scripts" / "offline_download.py",
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        fail("installation is incomplete; missing: " + ", ".join(missing))


def python_version(command: Tuple[str, ...]) -> Optional[Tuple[int, int, int]]:
    try:
        completed = subprocess.run(
            [*command, "-c", "import sys; print('.'.join(map(str, sys.version_info[:3])))"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    value = completed.stdout.strip().splitlines()[-1] if completed.stdout.strip() else ""
    try:
        major, minor, micro = value.split(".", 2)
        return int(major), int(minor), int(micro)
    except ValueError:
        return None


def dependency_python_candidates() -> list[Tuple[str, ...]]:
    commands: list[Tuple[str, ...]] = [(sys.executable,)]
    if os.name == "nt":
        commands.extend([("py", "-3.14"), ("py", "-3.13"), ("py", "-3.12")])
    else:
        commands.extend([("python3.14",), ("python3.13",), ("python3.12",), ("python3",), ("python",)])

    seen = set()
    unique = []
    for command in commands:
        key = tuple(command)
        if key in seen:
            continue
        seen.add(key)
        unique.append(command)
    return unique


def find_dependency_python() -> Optional[Tuple[str, ...]]:
    for command in dependency_python_candidates():
        version = python_version(command)
        if version and version >= MIN_DEPENDENCY_PYTHON:
            return command
    return None


def display_command(command: Tuple[str, ...]) -> str:
    return " ".join(f'"{part}"' if " " in part else part for part in command)


def venv_python_path(skill_dir: Path) -> Path:
    if os.name == "nt":
        return skill_dir / VENV_DIR_NAME / "Scripts" / "python.exe"
    return skill_dir / VENV_DIR_NAME / "bin" / "python"


def verify_p115client(python: Path) -> bool:
    try:
        subprocess.run(
            [str(python), "-c", "import p115client"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return False
    return True


def create_venv_with_python(python: Tuple[str, ...], skill_dir: Path, requirements: Path) -> Optional[Path]:
    venv_dir = skill_dir / VENV_DIR_NAME
    venv_python = venv_python_path(skill_dir)
    print(f"Creating skill Python environment: {venv_dir}")
    try:
        subprocess.run([*python, "-m", "venv", str(venv_dir)], check=True)
        subprocess.run([str(venv_python), "-m", "pip", "install", "--upgrade", "pip"], check=True)
        subprocess.run([str(venv_python), "-m", "pip", "install", "-r", str(requirements)], check=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"Warning: failed to create/install skill Python environment with {display_command(python)}: {exc}")
        return None
    if not verify_p115client(venv_python):
        print(f"Warning: p115client verification failed in {venv_python}")
        return None
    print(f"Installed p115client into skill environment: {venv_python}")
    return venv_python


def uv_candidates() -> list[Tuple[str, ...]]:
    candidates: list[Tuple[str, ...]] = [("uv",), (sys.executable, "-m", "uv")]
    seen = set()
    unique = []
    for command in candidates:
        if command in seen:
            continue
        seen.add(command)
        unique.append(command)
    return unique


def command_works(command: Tuple[str, ...], *args: str) -> bool:
    try:
        subprocess.run([*command, *args], check=True, capture_output=True, text=True)
    except (OSError, subprocess.CalledProcessError):
        return False
    return True


def find_uv() -> Optional[Tuple[str, ...]]:
    for command in uv_candidates():
        if command_works(command, "--version"):
            return command
    return None


def ensure_uv(allow_bootstrap: bool) -> Optional[Tuple[str, ...]]:
    uv = find_uv()
    if uv:
        return uv
    if not allow_bootstrap:
        return None
    print("Python 3.12+ was not found; installing uv with the current Python to bootstrap one...")
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", "--user", "uv"], check=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"Warning: failed to bootstrap uv automatically: {exc}")
        return None
    return find_uv()


def create_venv_with_uv(
    uv: Tuple[str, ...],
    skill_dir: Path,
    requirements: Path,
) -> Optional[Path]:
    venv_dir = skill_dir / VENV_DIR_NAME
    venv_python = venv_python_path(skill_dir)
    print(f"Creating skill Python 3.12 environment with uv: {venv_dir}")
    try:
        subprocess.run([*uv, "venv", "--python", "3.12", str(venv_dir)], check=True)
        subprocess.run([*uv, "pip", "install", "--python", str(venv_python), "-r", str(requirements)], check=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"Warning: failed to create/install skill environment with uv: {exc}")
        return None
    if not verify_p115client(venv_python):
        print(f"Warning: p115client verification failed in {venv_python}")
        return None
    print(f"Installed p115client into skill environment: {venv_python}")
    return venv_python


def install_dependencies(skill_dir: Path, skip_deps: bool) -> None:
    if skip_deps:
        print("Skipped Python dependency installation because --no-deps was set.")
        return

    requirements = skill_dir / "requirements.txt"
    if not requirements.exists():
        print("No requirements.txt found; skipped Python dependency installation.")
        return

    python = find_dependency_python()
    required = ".".join(map(str, MIN_DEPENDENCY_PYTHON))
    if python and create_venv_with_python(python, skill_dir, requirements):
        return

    uv = ensure_uv(allow_bootstrap=True)
    if uv and create_venv_with_uv(uv, skill_dir, requirements):
        return

    print(
        f"Warning: could not install p115client automatically because Python {required}+ "
        "and uv bootstrap were unavailable or failed.\n"
        "QR login still works with the system Python because scripts/login.py uses only the standard library.\n"
        "Install Python 3.12+ or uv, then rerun this installer."
    )


def compile_scripts(skill_dir: Path) -> None:
    scripts_dir = skill_dir / "scripts"
    scripts = sorted(scripts_dir.glob("*.py"))
    if not scripts:
        return
    try:
        subprocess.run([sys.executable, "-m", "py_compile", *map(str, scripts)], check=True)
        print(f"Verified Python script syntax with {sys.executable}.")
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"Warning: Python script syntax verification failed: {exc}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Install the 115-netdisk Codex skill")
    parser.add_argument("--repo", help="GitHub repo in OWNER/REPO format")
    parser.add_argument("--branch", "--ref", dest="ref", default=None, help="GitHub branch/ref, default: main")
    parser.add_argument("--skill-url", help="Raw or GitHub URL pointing to root SKILL.md or 115-netdisk/SKILL.md")
    parser.add_argument("--archive-url", help="Explicit zip archive URL")
    parser.add_argument("--source-dir", help="Install from a local checkout instead of GitHub")
    parser.add_argument("--target-root", default=str(default_target_root()), help="Skills root directory")
    parser.add_argument("--no-deps", action="store_true", help="Skip automatic p115client installation")
    args = parser.parse_args()

    owner = repo = ref = None
    if args.skill_url:
        owner, repo, ref = parse_github_skill_url(args.skill_url)
    if args.repo:
        owner, repo = parse_repo(args.repo)
    if args.ref:
        ref = args.ref
    if not ref:
        ref = "main"

    target_root = Path(args.target_root).expanduser().resolve()
    target_dir = target_root / SKILL_NAME

    with tempfile.TemporaryDirectory(prefix="115-netdisk-install-") as tmp:
        staging = Path(tmp) / "staging"
        staging.mkdir(parents=True, exist_ok=True)

        if args.source_dir:
            stage_from_source_dir(Path(args.source_dir), staging)
        else:
            if not owner or not repo or not ref:
                fail("provide --repo OWNER/REPO, --skill-url, or --source-dir")
            archive = download_archive(owner, repo, ref, args.archive_url)
            stage_from_zip(archive, staging)

        verify_install(staging / SKILL_NAME)
        target_root.mkdir(parents=True, exist_ok=True)
        if target_dir.exists():
            shutil.rmtree(target_dir)
        shutil.copytree(staging / SKILL_NAME, target_dir)

    verify_install(target_dir)
    compile_scripts(target_dir)
    install_dependencies(target_dir, args.no_deps)
    print(f"Installed {SKILL_NAME} skill to: {target_dir}")
    print("First use will start 115 QR login automatically if ~/.115-cookies is missing or empty.")
    print(f"Manual login command: {sys.executable} \"{target_dir / 'scripts' / 'login.py'}\" --no-open")


if __name__ == "__main__":
    main()

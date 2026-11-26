"""예시 이미지를 만드는 뒷단: fake, codex, openai. 고르는 법은 AX_IMAGE(없으면 AX_LLM을 따른다).

- fake: 코드가 만든 작은 단색 PNG. 바깥을 부르지 않는다.
- codex: Codex CLI의 이미지 생성 기능. llm/codex.py와 같은 격리(임시 CODEX_HOME, 로그인 파일 쓰기 금지)를
  따르되 image_generation만 켠다. 그림은 $CODEX_HOME/generated_images/<thread id>/*.png에 남는다.
- openai: 대회 게이트웨이의 {base_url}/images/generations. 주소와 키는 llm/openai_api.py와 같은 방식으로 읽는다.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import shutil
import struct
import sys
import tempfile
import zlib
from pathlib import Path

from httpx2 import AsyncClient

from llm.base import LLMError

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


class Unavailable(Exception):
    """이 뒷단으로는 이미지를 만들 수 없다(꺼짐, 지원하지 않음)."""


class ImageError(Exception):
    """만들다 실패했다. 메시지는 화면과 로그에 그대로 내도 되는 짧은 까닭이다."""


def backend_name() -> str:
    name = os.environ.get("AX_IMAGE", "").strip().lower()
    if name:
        return name
    return {"codex": "codex", "openai": "openai", "fake": "fake"}.get(os.environ.get("AX_LLM", "openai"), "off")


def unavailable_reason(name: str | None = None) -> str | None:
    name = name or backend_name()
    if name in ("fake", "codex", "openai"):
        if name == "codex" and shutil.which("codex") is None:
            return "Codex CLI가 없어 예시 이미지를 만들 수 없어요"
        return None
    if name == "off":
        return "지금 설정(AX_LLM=cli)에서는 예시 이미지를 만들지 않아요"
    return f"알 수 없는 이미지 설정이에요 (AX_IMAGE={name})"


async def generate(prompt: str, *, timeout: float) -> tuple[bytes, str]:
    """(PNG 바이트, 뒷단 이름)."""
    name = backend_name()
    reason = unavailable_reason(name)
    if reason:
        raise Unavailable(reason)
    if name == "fake":
        return fake_png(prompt), name
    if name == "codex":
        return await codex_image(prompt, timeout=timeout), name
    return await openai_image(prompt, timeout=timeout), name


# ---------- fake ----------


def fake_png(prompt: str, size: int = 64) -> bytes:
    """시키는 글로 색을 정한 단색 PNG."""
    h = zlib.crc32(prompt.encode("utf-8"))
    rgb = bytes(((h >> 16) & 0xFF, (h >> 8) & 0xFF, h & 0xFF))
    raw = b"".join(b"\x00" + rgb * size for _ in range(size))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    return (PNG_MAGIC + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


# ---------- codex ----------

_CODEX_DISABLED = (
    "shell_tool", "shell_snapshot", "view_image", "hooks", "plugins", "apps", "browser_use", "computer_use",
    "multi_agent", "multi_agent_v2", "goals", "tool_suggest", "workspace_dependencies",
)
_CODEX_CONFIG = (
    'model_provider="openai"', 'forced_login_method="chatgpt"', 'cli_auth_credentials_store="file"',
    'approval_policy="never"', 'mcp_servers={}', 'plugins={}', 'project_doc_max_bytes=0', 'web_search="disabled"',
    'include_environment_context=false', 'include_permissions_instructions=false',
    'analytics.enabled=false', 'otel.log_user_prompt=false', 'model_reasoning_effort="low"',
)
_CODEX_ASK = ("Use the image generation tool exactly once to create the image described below, then reply with "
              "the single word done. Do nothing else.\n\nImage: ")


def _codex_command(root: Path) -> tuple[list[str], dict[str, str], Path]:
    from llm.codex import _MAC_SANDBOX
    from llm.models import model_for

    executable = shutil.which("codex")
    if executable is None:
        raise Unavailable("Codex CLI가 없어 예시 이미지를 만들 수 없어요")
    login_home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex").resolve()
    login_file = (login_home / "auth.json").resolve()
    home = root / "codex"
    home.mkdir()
    (home / "auth.json").symlink_to(login_file)
    workdir = root / "work"
    workdir.mkdir()
    if sys.platform == "darwin":
        sandbox = ["/usr/bin/sandbox-exec", "-D", f"LOGIN_HOME={login_home}", "-D", f"LOGIN_FILE={login_file}",
                   "-p", _MAC_SANDBOX]
    elif sys.platform == "linux" and (bwrap := shutil.which("bwrap")):
        sandbox = [bwrap, "--ro-bind", "/", "/", "--bind", str(root), str(root), "--dev", "/dev", "--proc", "/proc", "--"]
    else:
        raise Unavailable("이 컴퓨터에서는 Codex 격리 실행기를 쓸 수 없어요")
    # 대회 키, 게이트웨이 주소는 넘기지 않는다.
    env = {key: os.environ[key] for key in ("PATH", "LANG", "LC_ALL", "LC_CTYPE") if key in os.environ}
    env.update(HOME=str(root), CODEX_HOME=str(home), TMPDIR=str(root), CODEX_EXEC_SERVER_URL="none")
    command = [*sandbox, executable, "exec", "--ignore-user-config", "--ignore-rules",
               "--skip-git-repo-check", "--sandbox", "read-only", "--json", "--color", "never",
               "--model", model_for("plan", backend="codex").model, "--enable", "image_generation"]
    for item in _CODEX_CONFIG:
        command.extend(("-c", item))
    for feature in _CODEX_DISABLED:
        command.extend(("--disable", feature))
    command.append("-")
    return command, env, workdir


async def codex_image(prompt: str, *, timeout: float) -> bytes:
    from llm.cli import _kill

    with tempfile.TemporaryDirectory(prefix="chilseong-image-", dir="/tmp") as temp:
        root = Path(temp).resolve()
        command, env, workdir = _codex_command(root)
        try:
            proc = await asyncio.create_subprocess_exec(
                *command, env=env, cwd=workdir, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE, start_new_session=True)
        except OSError:
            raise ImageError("Codex 실행 환경을 준비하지 못했어요") from None
        try:
            async with asyncio.timeout(timeout):
                stdout, _ = await proc.communicate((_CODEX_ASK + prompt).encode("utf-8"))
        except (TimeoutError, asyncio.CancelledError):
            _kill(proc)
            await proc.communicate()
            raise
        thread = None
        for line in stdout.splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if isinstance(event, dict) and event.get("type") == "thread.started":
                thread = event.get("thread_id")
        images = root / "codex" / "generated_images"
        found = sorted((images / thread).glob("*.png") if isinstance(thread, str) and thread and "/" not in thread
                       else [], key=lambda p: p.stat().st_mtime)
        if not found:
            found = sorted(images.glob("*/*.png"), key=lambda p: p.stat().st_mtime) if images.exists() else []
        if not found:
            raise ImageError("Codex가 이미지를 남기지 않았어요" if proc.returncode == 0 else "Codex 호출에 실패했어요")
        data = found[-1].read_bytes()
        if not data.startswith(PNG_MAGIC):
            raise ImageError("Codex가 남긴 파일이 PNG가 아니에요")
        return data


# ---------- openai (대회 게이트웨이) ----------

IMAGE_SIZE = "1024x1024"


def openai_request(prompt: str) -> dict:
    from llm.models import model_for

    model = model_for("image", backend="openai").model
    request = {"model": model, "prompt": prompt, "n": 1, "size": IMAGE_SIZE}
    if not model.startswith("gpt-image"):
        # gpt-image 계열은 늘 b64_json으로 돌려주고 response_format을 받지 않는다.
        request["response_format"] = "b64_json"
    return request


async def openai_image(prompt: str, *, timeout: float) -> bytes:
    from llm.openai_api import _credentials

    try:
        url, key = _credentials()
    except LLMError as exc:
        raise ImageError(str(exc)) from None
    endpoint = url.copy_with(path=url.path.rstrip("/") + "/images/generations")  # 주소의 query는 그대로 둔다
    try:
        async with AsyncClient(follow_redirects=False, trust_env=False, timeout=timeout) as http:
            response = await http.post(str(endpoint), json=openai_request(prompt),
                                       headers={"Authorization": f"Bearer {key}"})
    except Exception as exc:  # 연결 오류의 본문에 주소나 헤더가 들 수 있어 까닭만 남긴다
        if isinstance(exc, (TimeoutError, asyncio.CancelledError)):
            raise
        raise ImageError("대회 게이트웨이에 연결하지 못했어요") from None
    if response.status_code == 404:
        raise ImageError("대회 게이트웨이가 이미지 생성을 지원하지 않아요 (HTTP 404)")
    if response.status_code != 200:
        raise ImageError(f"대회 게이트웨이 이미지 요청에 실패했어요 (HTTP {response.status_code})")
    try:
        b64 = response.json()["data"][0]["b64_json"]
        data = base64.b64decode(b64, validate=True)
    except (ValueError, KeyError, IndexError, TypeError):
        raise ImageError("대회 게이트웨이의 이미지 응답을 읽지 못했어요") from None
    if not data.startswith(PNG_MAGIC):
        raise ImageError("대회 게이트웨이가 준 이미지가 PNG가 아니에요")
    return data

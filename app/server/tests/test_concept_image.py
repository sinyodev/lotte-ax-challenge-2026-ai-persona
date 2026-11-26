"""컨셉의 예시 이미지: 시키는 글, fake 뒷단의 길, 경로 탈출, off, openai 요청 모양(가짜 전송)."""

import asyncio
import base64
import json

import httpx
import pytest
from fastapi.testclient import TestClient

import chats
from imagegen import backends, prompt, store
from llm import openai_api
from main import app

CONCEPT = {
    "id": "a", "name": "밀키스 화채", "headline": "여름 외식에 곁들이는 화채 한 캔",
    "benefit": "진한 단맛 뒤 입안이 개운해요", "points": ["수박화채 맛", "수박과 복숭아 향", "부드러운 탄산"],
    "price": "1,200원", "pack": "250ml 캔", "_flavor": "수박화채맛", "_container": "캔", "_volume": 250,
    "_carb": "약함", "_own": "밀키스 오리지널 250mL 캔 830원 2+1",
    "variants": [{"container": "캔", "pack": "슬림캔", "volume_ml": 250, "price": 1200},
                 {"container": "페트", "pack": "PET", "volume_ml": 500, "price": 1800}],
    "_shelf_variant": 0, "season": "5~9월 한정", "storage": "상온",
}
NOTE = {"kind": "탄산음료", "shelf_kind": "탄산", "product": {"value": "밀키스 화채"}}


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "IMAGES_DIR", tmp_path / "images")
    monkeypatch.delenv("AX_IMAGE", raising=False)
    chats.STORE_DIR.mkdir(parents=True, exist_ok=True)
    rec = {"id": "chat1", "messages": [], "note": {**NOTE, "concepts": [CONCEPT]}}
    (chats.STORE_DIR / "chat1.json").write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
    return TestClient(app)


def test_prompt_has_no_brand_and_forbids_text():
    text = prompt.build(CONCEPT, NOTE)
    assert not prompt.BRANDS.search(text)
    for word in ("밀키스", "Milkis", "롯데", "칠성"):
        assert word.lower() not in text.lower()
    assert "no text" in text and "no logo" in text and "no trademark" in text
    assert "slim aluminum can" in text and "250 ml" in text
    assert "watermelon" in text and "peach" in text
    assert "bubbles" in text
    assert text.isascii()  # 컨셉의 글을 그대로 넣지 않는다


def test_prompt_is_stable_and_follows_shelf_variant():
    assert prompt.build(CONCEPT, NOTE) == prompt.build(dict(CONCEPT), dict(NOTE))
    pet = prompt.build({**CONCEPT, "_shelf_variant": 1}, NOTE)
    assert "clear plastic bottle" in pet and "500 ml" in pet


def test_prompt_green_grape_not_grape():
    text = prompt.build({"id": "b", "name": "청포도 에이드", "points": []}, {"kind": "주스"})
    assert "green grape" in text and ", grape" not in text and "fruit juice" in text


def test_fake_post_get_status(client):
    base = "/api/chats/chat1/concepts/a/image"
    assert client.get(base + "/status").json() == {"status": "none"}
    assert client.get(base).status_code == 404
    r = client.post(base, json={})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ready" and body["version"] == 1 and body["url"].startswith(base)
    img = client.get(base)
    assert img.status_code == 200 and img.headers["content-type"] == "image/png"
    assert img.content.startswith(backends.PNG_MAGIC)
    assert client.get(base + "/status").json()["status"] == "ready"
    # 다시 누르면 있는 것을 준다. again이면 새로 만든다
    assert client.post(base).json()["version"] == 1
    assert client.post(base, json={"again": True}).json()["version"] == 2
    info = json.loads((store.IMAGES_DIR / "chat1" / "a.json").read_text(encoding="utf-8"))
    assert info["backend"] == "fake" and "no logo" in info["prompt"]


def test_unknown_chat_or_concept(client):
    assert client.post("/api/chats/chat1/concepts/zz/image").status_code == 404
    assert client.post("/api/chats/nochat/concepts/a/image").status_code == 404


@pytest.mark.parametrize("path", [
    "/api/chats/..%2F..%2Fetc/concepts/a/image",
    "/api/chats/chat1/concepts/..%2Fx/image",
    "/api/chats/chat1/concepts/a.b/image",
])
def test_path_escape_rejected(client, path):
    assert client.get(path).status_code in (400, 404)
    assert client.post(path).status_code in (400, 404, 405)


def test_store_rejects_unsafe_ids(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "IMAGES_DIR", tmp_path)
    with pytest.raises(ValueError):
        store.save("../x", "a", b"", prompt="", backend="fake", sec=0)


def test_off_is_409(client, monkeypatch):
    monkeypatch.setenv("AX_LLM", "cli")
    r = client.post("/api/chats/chat1/concepts/a/image")
    assert r.status_code == 409 and r.json()["detail"]
    assert client.get("/api/chats/chat1/concepts/a/image/status").json() == {"status": "unavailable"}


def test_backend_follows_ax_llm(monkeypatch):
    for llm, image in (("codex", "codex"), ("openai", "openai"), ("fake", "fake"), ("cli", "off")):
        monkeypatch.setenv("AX_LLM", llm)
        assert backends.backend_name() == image
    monkeypatch.setenv("AX_IMAGE", "fake")
    assert backends.backend_name() == "fake"


def test_backend_error_is_502(client, monkeypatch):
    async def broken(_prompt, *, timeout):
        raise backends.ImageError("뒷단 오류")

    monkeypatch.setattr(backends, "generate", broken)
    r = client.post("/api/chats/chat1/concepts/a/image")
    assert r.status_code == 502 and r.json()["detail"] == "뒷단 오류"


def test_openai_request_shape_with_fake_transport(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_BASE_URL", "https://gateway.fixture.invalid/v1?team=x")
    monkeypatch.setenv("OPENAI_API_KEY", "fixture-authorization-value")
    monkeypatch.setattr(openai_api, "_ENV_FILE", tmp_path / ".env.local")
    monkeypatch.delenv("AX_MODEL_IMAGE", raising=False)
    png = backends.fake_png("x")
    seen = []

    async def handle(request):
        seen.append(request)
        return httpx.Response(200, json={"data": [{"b64_json": base64.b64encode(png).decode()}]})

    monkeypatch.setattr(backends, "AsyncClient", lambda **options: httpx.AsyncClient(
        transport=httpx.MockTransport(handle), **options))
    data = asyncio.run(backends.openai_image("a can", timeout=5))
    assert data == png
    (req,) = seen
    assert req.method == "POST" and req.url.path == "/v1/images/generations"
    assert req.url.host == "gateway.fixture.invalid" and req.url.params["team"] == "x"
    assert req.headers["authorization"] == "Bearer fixture-authorization-value"
    body = json.loads(req.content)
    assert body == {"model": "gpt-image-1", "prompt": "a can", "n": 1, "size": "1024x1024"}

    monkeypatch.setenv("AX_MODEL_IMAGE", "dall-e-3")
    assert backends.openai_request("p")["response_format"] == "b64_json"


def test_openai_404_is_readable(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_BASE_URL", "https://gateway.fixture.invalid/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "fixture-authorization-value")
    monkeypatch.setattr(openai_api, "_ENV_FILE", tmp_path / ".env.local")

    async def handle(_request):
        return httpx.Response(404, json={"error": "nope"})

    monkeypatch.setattr(backends, "AsyncClient", lambda **options: httpx.AsyncClient(
        transport=httpx.MockTransport(handle), **options))
    with pytest.raises(backends.ImageError, match="지원하지 않아요"):
        asyncio.run(backends.openai_image("a can", timeout=5))

"""W3 보드의 자료 합치기, 조회, 수동 수정과 저장을 견본으로 검증한다."""

import base64
import csv
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import pytest
from docx import Document
from fastapi import FastAPI
from fastapi.testclient import TestClient
from openpyxl import Workbook

import chats
from ideas import store
from llm.base import get_llm, set_llm
from llm.fake import FakeLLM
from onsite.schema import CSV_COLUMNS
from routes.ideas import router
from shelftest import method
from shelftest import store as runs


@pytest.fixture
def ideas_client(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "STORE_DIR", tmp_path / "ideas")
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _assets(monkeypatch, path: Path, rows: list[dict]):
    path.mkdir(exist_ok=True)
    monkeypatch.setenv("AX_ONSITE_DIR", str(path))
    with (path / "assets.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=CSV_COLUMNS["assets"])
        writer.writeheader()
        writer.writerows(rows)


def _chat(chat_id: str, *, confirmed: bool = True):
    chats.save({
        "id": chat_id, "created_at": "2026-02-01T09:00:00+09:00", "updated_at": "2026-02-05T09:00:00+09:00",
        "note": {"confirmed": confirmed, "shelf_kind": "탄산", "concepts": [
            {"id": "a", "name": "견본 유자 소다", "pack": "250ml 캔", "price": "1,400원", "points": ["유자 향"]},
            {"id": "b", "name": "견본 매실 소다", "volume": "500ml 페트", "price": "1,700원"},
        ]},
    })


def _run(run_id: str, *, status: str, stamp: str, answers: list[tuple[str, str | None]], concept_id: str = "a"):
    runs.save_meta({"id": run_id, "chat_id": "chat-1", "concept_id": concept_id,
                    "status": status, "updated_at": stamp, "line": "concept", "concept": {"name": "보고용 소다"},
                    "shelf_products": [["own", "견본 자사 제품", True], ["rival", "견본 경쟁 제품", False]]})
    for i, (chosen, before) in enumerate(answers):
        runs.append_answer(run_id, {"visit": str(i), "cond": method.CONCEPT, "product": chosen})
        if before is not None:
            runs.append_answer(run_id, {"visit": str(i), "cond": method.BASELINE, "product": before})


def test_chat_rows_follow_each_concepts_latest_completed_run(ideas_client):
    _chat("chat-1")
    _chat("draft", confirmed=False)
    url = "/api/ideas"
    first = ideas_client.get(url).json()["items"]
    assert len(first) == 2
    before = next(row for row in first if "유자" in row["name"])
    assert before["status"] == "기획 중"
    assert before["last_test"] is None
    assert not store.STORE_DIR.exists()

    edited = ideas_client.patch(f"{url}/{before['id']}", json={"owner": "상품기획팀", "checks": {"qual": True}})
    assert edited.status_code == 200
    _run("run-000000000001", status="done", stamp="2026-02-06T00:00:00Z", answers=[("concept", "own")])
    _run("run-000000000002", status="done", stamp="2026-02-07T00:00:00Z",
         answers=[("concept", "own"), ("concept", "rival"), ("rival", "own")])
    _run("run-000000000003", status="running", stamp="2026-02-08T00:00:00Z", answers=[("concept", "rival")])
    _run("run-000000000004", status="done", stamp="2026-02-09T00:00:00Z", answers=[])
    _run("run-000000000005", status="done", stamp="2026-02-06T00:00:00Z", answers=[("rival", "own")], concept_id="b")

    rows = ideas_client.get(url).json()["items"]
    current = next(row for row in rows if row["id"] == before["id"])
    assert current["source"] == "chat" and current["chat_id"] == "chat-1"
    assert current["status"] == "가상 테스트 완료" and current["owner"] == "상품기획팀"
    assert current["checks"] == {"virtual_test": True, "qual": True, "quant": False, "launched": False}
    assert current["last_test"] == {"selection_rate": 2 / 3, "own_share": 0.5, "virtual_sales": None}
    older = next(row for row in rows if row["id"] != before["id"])
    assert older["pack"] == "500ml 페트"
    assert older["last_test"] == {"selection_rate": 0, "own_share": None, "virtual_sales": None}
    dashboard = ideas_client.get(f"{url}/dashboard").json()
    assert [row["id"] for row in dashboard["recent"]] == [current["id"], older["id"]]
    assert dashboard["funnel"] == {"ideas": 2, "virtual_test": 2, "research": 1, "launched": 0}


def test_assets_mapping_missing_reason_and_dashboard_updates(ideas_client, monkeypatch, tmp_path):
    path = tmp_path / "onsite"
    rows = [
        {"asset_id": "shared-1", "sku": "shared", "name": "견본 구연산 소다", "brand": "견본", "category": "탄산",
         "status": "운영", "launched": "2021-05-01"},
        {"asset_id": "shared-2", "sku": "shared", "name": "견본 구연산 소다 개정", "brand": "견본", "category": "탄산",
         "status": "개발중단"},
        {"asset_id": "other-1", "name": "견본 보리음료", "status": "단종", "reason": "낮은 회전으로 판매 부진"},
        {"asset_id": "new-1", "name": "견본 바닐라차", "status": "아이디어"},
    ]
    _assets(monkeypatch, path, rows)
    original = (path / "assets.csv").read_bytes()
    url = "/api/ideas"
    by_id = {row["id"]: row for row in ideas_client.get(url).json()["items"]}
    assert [by_id["assets-" + row["asset_id"]]["status"] for row in rows] == ["출시", "폐기", "단종", "기획 중"]
    assert by_id["assets-shared-2"]["reason"] is None
    assert by_id["assets-shared-1"]["checks"]["launched"] is True
    assert by_id["assets-other-1"]["checks"]["launched"] is True
    assert not store.STORE_DIR.exists()
    before = ideas_client.get(f"{url}/dashboard").json()
    assert before["reason_counts"] == {"수요 부족": 1, "사유 기록 없음": 1}
    assert before["brand_counts"] == {"견본": 2}
    assert before["category_counts"] == {"탄산": 2}

    edit = ideas_client.patch(f"{url}/assets-new-1", json={"status": "폐기", "reason": "사업성 부족",
                                                         "checks": {"virtual_test": True}})
    assert edit.status_code == 200
    after = ideas_client.get(f"{url}/dashboard").json()
    assert after["funnel"] == {"ideas": 4, "virtual_test": 1, "research": 0, "launched": 2}
    assert after["status_counts"]["폐기"] == 2
    assert after["reason_counts"]["사업성 부족"] == 1
    assert after["skipped_research_count"] == 1 and after["max_saved_won"] == 20_000_000
    assert (path / "assets.csv").read_bytes() == original
    _assets(monkeypatch, path, rows + [{"asset_id": "late-1", "name": "뒤늦게 추가한 자산", "status": "운영"}])
    assert len(ideas_client.get(url).json()["items"]) == 5


def test_similarity_can_match_a_flavor_or_format_across_brands_and_categories(ideas_client, monkeypatch, tmp_path):
    _assets(monkeypatch, tmp_path / "onsite", [
        {"asset_id": "a", "name": "비교용 과일 소다", "brand": "초록", "category": "투명 탄산", "pack": "PET 500mL",
         "concept": "유자 제스트 향의 시즌 한정 음료", "status": "단종"},
        {"asset_id": "b", "name": "비교용 얼음 파우치", "brand": "샘플", "category": "차", "pack": "150ml 파우치",
         "concept": "얼려서 먹는 차 음료", "status": "개발중단"},
        {"asset_id": "c", "name": "비교용 보리차", "category": "차", "pack": "500ml 페트", "status": "단종"},
    ])
    url = "/api/ideas/similar"
    hit = ideas_client.get(url, params={"name": "여름 유자 탄산", "brand": "초록", "category": "탄산", "pack": "500ml 페트",
                                        "flavor": "유자 맛", "price": "1,400원"}).json()["items"]
    assert [row["id"] for row in hit] == ["assets-a"]
    assert hit[0]["score"] > 0
    assert {"같은 브랜드", "같은 종류", "같은 용기", "같은 용량", "맛·향: 유자"} <= set(hit[0]["matches"])

    cross = ideas_client.get(url, params={"name": "프리즈 커피", "category": "커피", "pack": "파우치"}).json()["items"]
    assert [row["id"] for row in cross] == ["assets-b"]
    assert "얼려 먹는 형태" in cross[0]["matches"]
    assert ideas_client.get(url).json() == {"items": []}


def test_atomic_commit_and_concurrent_edits_are_idempotent(ideas_client):
    url = "/api/ideas"
    commit = f"{url}/import/commit"
    added = {"name": "견본 생강 소다", "price": "2,000원", "checks": {"virtual_test": True}}
    invalid = ideas_client.post(commit, json={"items": [added, {"name": ""}]})
    assert invalid.status_code == 422
    assert ideas_client.get(url).json() == {"items": []}
    assert not store.STORE_DIR.exists()
    with ThreadPoolExecutor(max_workers=2) as pool:
        result = list(pool.map(lambda _: ideas_client.post(commit, json={"items": [added, added]}).json(), range(2)))
    assert result[0] == result[1]
    assert len(result[0]["items"]) == 1
    row_id = result[0]["items"][0]["id"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        replies = list(pool.map(lambda update: ideas_client.patch(f"{url}/{row_id}", json=update), [
            {"checks": {"qual": True}, "status": "소비자 조사 진행"}, {"checks": {"quant": True}, "owner": "견본 담당"},
        ]))
    assert all(reply.status_code == 200 for reply in replies)
    row = ideas_client.get(url).json()["items"][0]
    assert row["checks"] == {"virtual_test": True, "qual": True, "quant": True, "launched": False}
    assert row["owner"] == "견본 담당" and row["status"] == "소비자 조사 진행"
    assert ideas_client.post(commit, json={"items": [added]}).json()["items"] == [row]
    assert ideas_client.patch(f"{url}/{row_id}", json={"owner": "견본 담당"}).json() == row
    assert ideas_client.patch(f"{url}/{row_id}", json={"owner": None}).json()["owner"] is None
    assert ideas_client.patch(f"{url}/missing", json={"status": "보류"}).status_code == 404
    assert ideas_client.patch(f"{url}/{row_id}", json={"status": "알 수 없음"}).status_code == 422


def test_import_paste_recovers_rows_and_previews_duplicate_candidates(ideas_client, monkeypatch, tmp_path):
    _assets(monkeypatch, tmp_path / "onsite", [
        {"asset_id": "a", "name": "견본 자두 탄산", "brand": "견본", "status": "단종"},
    ])
    url = "/api/ideas/import"
    prompt = ideas_client.get(f"{url}/prompt").json()["prompt"]
    assert all(word in prompt for word in ("사유", "금액", "단위", "행을 나누고", "qual", "selection_rate"))
    preview = ideas_client.post(f"{url}/preview", json={"text": """온 답이에요.
```json
{"items": [{"제품명": "견본 자두탄산", "가격": "1,200원", "상태": "정성 조사 진행"},
           {"name": broken},
           {"name": "검수 전 안", "price": "2200", "last_test": {"selection_rate": "20%"},},]}
```
"""}).json()
    assert len(preview["items"]) == 2 and preview["warnings"]
    first, second = preview["items"]
    assert first["row"]["status"] == "소비자 조사 진행" and first["row"]["checks"]["qual"] is True
    assert first["row"]["reason"] is None and "reason" in first["missing"]
    assert first["duplicates"] == [{"id": "assets-a", "name": "견본 자두 탄산"}]
    assert second["row"]["price"] is None and "price" in second["missing"]
    assert second["row"]["last_test"]["selection_rate"] == 0.2
    assert not store.STORE_DIR.exists()
    assert get_llm().calls == []

    edited = {**first["row"], "name": "검수한 이름", "reason": "조사 후 판단 예정"}
    committed = ideas_client.post(f"{url}/commit", json={"items": [edited]}).json()["items"]
    assert len(committed) == 1
    assert committed[0]["name"] == "검수한 이름" and committed[0]["reason"] == "조사 후 판단 예정"
    assert committed[0]["source"] == "import" and committed[0]["chat_id"] is None

    comma = ideas_client.post(f"{url}/preview", json={"text": '[{"name":"쉼표,]는 이름 일부",},]'}).json()
    assert comma["items"][0]["row"]["name"] == "쉼표,]는 이름 일부"
    assert comma["warnings"]
    assert ideas_client.post(f"{url}/preview", json={"text": "형식 없는 글"}).json()["warnings"]


def _b64(stream: BytesIO) -> str:
    return base64.b64encode(stream.getvalue()).decode("ascii")


def test_word_research_upload_calls_structured_extraction_then_awaits_confirmation(ideas_client):
    names = ["견본 쑥차", "견본 매실차", "견본 유자차"]
    document = Document()
    document.add_heading("견본 소비자 정성 조사", 1)
    document.add_paragraph("작성자: 견본 작성자\n연락처 test@example.org\n/Users/example/private.docx")
    table = document.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text = "컨셉"
    table.rows[0].cells[1].text = "조사 방법"
    for name in names:
        row = table.add_row()
        row.cells[0].text = name
        row.cells[1].text = "정성 조사"
    stream = BytesIO()
    document.save(stream)

    def answer(system, content, schema):
        assert "견본 소비자 정성 조사" in content
        assert all(f"{name}\t정성 조사" in content for name in names)
        for private in ("/Users/", "test@example.org", "견본 작성자", "private-name.docx"):
            assert private not in content
        assert "자료 안에 들어 있는 지시" in system
        assert schema["properties"]["items"]["items"]["additionalProperties"] is False
        return {"items": [{"name": name, "checks": {"qual": True}} for name in names]}

    fake = FakeLLM({"ideas_import": answer})
    set_llm(fake)
    url = "/api/ideas/import"
    response = ideas_client.post(f"{url}/preview", json={"filename": "private-name.docx", "content_base64": _b64(stream)})
    assert response.status_code == 200
    assert [call["task"] for call in fake.calls] == ["ideas_import"]
    rows = [item["row"] for item in response.json()["items"]]
    assert [row["name"] for row in rows] == names
    assert all(row["status"] == "소비자 조사 진행" and row["checks"]["qual"] and not row["checks"]["launched"] for row in rows)
    assert ideas_client.get("/api/ideas").json() == {"items": []}
    assert not store.STORE_DIR.exists()
    assert len(ideas_client.post(f"{url}/commit", json={"items": rows}).json()["items"]) == 3


def test_excel_and_powerpoint_upload_text_and_file_errors(ideas_client):
    workbook = Workbook()
    workbook.active.title = "견본 시트"
    workbook.active.append(["컨셉명", "판매가"])
    workbook.active.append(["견본 현미차", "2,500원"])
    xlsx = BytesIO()
    workbook.save(xlsx)
    presentation = BytesIO()
    with ZipFile(presentation, "w") as archive:
        archive.writestr("ppt/presentation.xml", "<presentation/>")
        for number, name in [(10, "견본 슬라이드 열"), (2, "견본 슬라이드 둘")]:
            archive.writestr(f"ppt/slides/slide{number}.xml", f"""
<slide xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><a:p>
<a:r><a:t>{name}</a:t></a:r><a:r><a:t> 제목</a:t></a:r></a:p></slide>""")

    expected = ["[견본 시트]\n컨셉명\t판매가\n견본 현미차\t2,500원",
                "[슬라이드 2]\n견본 슬라이드 둘 제목\n[슬라이드 10]\n견본 슬라이드 열 제목"]

    def answer(system, content, schema):
        assert content == expected.pop(0)
        return {"items": [{"name": "확인할 견본"}]}

    fake = FakeLLM({"ideas_import": answer})
    set_llm(fake)
    url = "/api/ideas/import/preview"
    for filename, stream in (("workbook.xlsx", xlsx), ("deck.pptx", presentation)):
        response = ideas_client.post(url, json={"filename": filename, "content_base64": _b64(stream)})
        assert response.status_code == 200 and response.json()["items"][0]["row"]["name"] == "확인할 견본"
    assert not expected
    assert ideas_client.post(url, json={"filename": "broken.docx", "content_base64": "???"}).status_code == 422
    assert ideas_client.post(url, json={"filename": "mixed.xlsx", "content_base64": _b64(presentation)}).status_code == 422
    assert ideas_client.post(url, json={"filename": "obsolete.xls", "content_base64": _b64(xlsx)}).status_code == 422
    assert len(fake.calls) == 2
    assert not store.STORE_DIR.exists()

    set_llm(FakeLLM())
    local_preview = ideas_client.post(url, json={"filename": "workbook.xlsx", "content_base64": _b64(xlsx)}).json()
    assert local_preview["items"][0]["row"]["name"] == "견본 현미차"
    assert local_preview["items"][0]["row"]["price"] == "2,500원"


def test_manual_idea_with_attached_progress_can_be_reopened_and_retried(ideas_client):
    from uuid import uuid4

    root = "/api/ideas"
    new = {"key": str(uuid4()), "name": "견본 아이디어"}
    row = ideas_client.post(root, json=new).json()
    assert ideas_client.post(root, json=new).json()["id"] == row["id"]
    assert len(ideas_client.get(root).json()["items"]) == 1
    path = f"{root}/{row['id']}"
    assert ideas_client.patch(path, json={"status": "소비자 조사 진행"}).is_success
    assert ideas_client.get(root + "/dashboard").json()["funnel"]["research"] == 1
    entry = {"key": str(uuid4()), "text": "초안 검토", "filename": "초안.txt", "content_base64": "YWJj"}
    assert ideas_client.post(path + "/logs", json=entry).is_success
    assert len(ideas_client.post(path + "/logs", json=entry).json()["items"]) == 1
    stored = ideas_client.get(path + "/logs").json()["items"][0]
    assert stored["filename"] == "초안.txt" and stored["text"] == "초안 검토"
    file = ideas_client.get(path + "/logs/" + entry["key"] + "/file")
    assert file.content == b"abc" and "attachment" in file.headers["content-disposition"]
    assert ideas_client.get(root).json()["items"][0]["attachment_count"] == 1
    assert ideas_client.post(path + "/logs", json={"key": str(uuid4())}).status_code == 422

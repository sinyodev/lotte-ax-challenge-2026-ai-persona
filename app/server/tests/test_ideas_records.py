"""출시일과 업무 기록을 합성 자료로 검증한다."""

import base64
import json
import sqlite3
from io import BytesIO
from uuid import uuid4

import pytest
from docx import Document
from fastapi import FastAPI
from fastapi.testclient import TestClient

import chats
from ideas import store
from llm.base import set_llm
from llm.fake import FakeLLM
from routes.ideas import router

ROOT = "/api/ideas"


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "STORE_DIR", tmp_path / "ideas")
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _create(client, *, name="견본 귤차", **fields):
    return client.post(ROOT, json={"key": str(uuid4()), "name": name, **fields}).json()


def _by_id(client):
    return {row["id"]: row for row in client.get(ROOT).json()["items"]}


def _b64(content: bytes) -> str:
    return base64.b64encode(content).decode("ascii")


def _docx(*paragraphs):
    document = Document()
    for paragraph in paragraphs:
        document.add_paragraph(paragraph)
    stream = BytesIO()
    document.save(stream)
    return _b64(stream.getvalue())


def test_launch_kpi_uses_first_actual_date_per_brand_and_product(client, monkeypatch):
    rows = [
        {"asset_id": "first", "name": "견본 배차 (250㎖)", "brand": " 새봄 ", "status": "단종",
         "concept": "구운 배 향을 살린 차", "launched": "2022-03-04", "ended": "2024-04-02"},
        {"asset_id": "later", "name": "견본 배차 1.5 L", "brand": "새봄", "status": "운영", "launched": "2024-02-03"},
        {"asset_id": "unknown", "name": "견본 배차 300mL", "brand": "새봄", "status": "운영"},
        {"asset_id": "other", "name": "견본 배차", "brand": "새빛", "status": "단종", "launched": "2023-02-29"},
        {"asset_id": "pending", "name": "견본 자두차", "brand": "새봄", "status": "개발중단", "launched": "2024-05-04"},
        {"asset_id": "concept", "name": "견본 제비차", "status": "아이디어", "launched": "2024-05-04"},
        {"asset_id": "future", "name": "견본 노을차", "status": "운영", "launched": "2099-05-04"},
    ]
    monkeypatch.setattr("ideas.board.onsite.load", lambda name: rows)
    listed = _by_id(client)
    assert listed["assets-first"]["concept"] == "구운 배 향을 살린 차"
    assert listed["assets-first"]["launched_on"] == "2022-03-04"
    assert listed["assets-first"]["reason"] is None
    assert listed["assets-other"]["launched_on"] is None
    assert listed["assets-concept"]["launched_on"] is None and listed["assets-pending"]["launched_on"] is None
    assert listed["assets-first"]["last_work"] is None and not store.STORE_DIR.exists()

    first = client.patch(f"{ROOT}/assets-first", json={"status": "기획 중"})
    assert first.json()["launched_on"] == "2022-03-04"
    dashboard = client.get(f"{ROOT}/dashboard").json()
    assert dashboard["launches"] == [{"name": rows[0]["name"], "row_id": "assets-first", "launched_on": "2022-03-04"}]
    assert dashboard["undated_launches"] == 1
    assert dashboard["funnel"]["launched"] == 2


def test_manual_changes_leave_one_atomic_audit_and_keep_the_launch_after_status_changes(client, monkeypatch):
    row = _create(client)
    endpoint = f"{ROOT}/{row['id']}"
    fields = {"status": "출시", "concept": "차갑게 즐기는 귤차", "launched_on": "2024-02-29", "reason": "검토 통과"}
    for day in ("2024-02", "2024-2-29", "2023-02-29", "2024-02-29T00:00:00Z"):
        assert client.patch(endpoint, json={"launched_on": day}).status_code == 422
    assert client.get(f"{endpoint}/logs").json() == {"items": []}

    edit = client.patch(endpoint, json=fields).json()
    assert client.patch(endpoint, json=fields).json() == edit
    logs = client.get(f"{endpoint}/logs").json()["items"]
    assert len(logs) == 1
    assert all(value in logs[0]["text"] for value in fields.values())
    assert (edit["last_work"], edit["work_date"]) == (logs[0]["text"], logs[0]["at"])

    def broken_audit(*args):
        raise sqlite3.OperationalError("합성 오류")

    with monkeypatch.context() as override:
        override.setattr(store, "_append_log", broken_audit)
        with pytest.raises(sqlite3.OperationalError):
            client.patch(endpoint, json={"status": "단종", "reason": "진열 계약 종료"})
    assert _by_id(client)[row["id"]] == edit
    assert client.get(f"{endpoint}/logs").json()["items"] == logs

    revised = client.patch(endpoint, json={"status": "정량 조사 중", "reason": None, "verdict": "추가 조사"}).json()
    assert revised["checks"]["launched"] is True
    assert revised["launched_on"] == "2024-02-29"
    assert revised["reason"] is None and revised["verdict"] == "추가 조사"
    assert client.get(f"{ROOT}/dashboard").json()["funnel"]["research"] == 1


def test_legacy_attachment_work_and_confirmed_decisions_survive_retries_and_manual_edits(client):
    row = _create(client)
    row_id = row["id"]
    endpoint = f"{ROOT}/{row_id}"
    file_id = str(uuid4())
    payload = _docx("합성 회의 결과", "개발 중단 확정. 사유: 용기 공급 계약 취소")
    at = "2023-04-01T07:00:00+00:00"
    with sqlite3.connect(store.STORE_DIR / "board.sqlite3") as db:
        (encoded,) = db.execute("SELECT row FROM imports WHERE id=?", (row_id,)).fetchone()
        snapshot = json.loads(encoded)
        for field in ("concept", "launched_on", "last_work", "work_date"):
            snapshot.pop(field)
        db.execute("UPDATE imports SET row=? WHERE id=?", (json.dumps(snapshot), row_id))
        db.execute("DROP TABLE log_decisions")
        db.execute("INSERT INTO worklog VALUES (?, ?, ?, '', ?, ?)",
                   (row_id, file_id, at, "마지막 회의.docx", base64.b64decode(payload)))

    legacy = _by_id(client)[row_id]
    assert (legacy["last_work"], legacy["work_date"], legacy["attachment_count"]) == ("마지막 회의.docx", at, 1)
    assert (legacy["status"], legacy["reason"]) == ("폐기", "용기 공급 계약 취소")
    assert client.get(f"{endpoint}/logs/{file_id}/file").content == base64.b64decode(payload)

    reopened = client.patch(endpoint, json={"status": "정성 조사 중", "reason": None}).json()
    assert reopened["status"] == "정성 조사 중" and reopened["reason"] is None
    draft = {"key": str(uuid4()), "text": "개발 중단 검토안\n개발 중단 사유: 원료 가격 상승 우려"}
    assert client.post(f"{endpoint}/logs", json=draft).is_success
    assert _by_id(client)[row_id]["status"] == "정성 조사 중"

    needed = {"key": str(uuid4()), "text": "용기 납품 취소로 개발을 중단했습니다."}
    log = client.post(f"{endpoint}/logs", json=needed).json()["items"][0]
    assert client.post(f"{endpoint}/logs", json={**needed, "text": "재전송에서 달라진 문구"}).json()["items"][0] == log
    final = _by_id(client)[row_id]
    assert (final["status"], final["reason"]) == ("폐기", "용기 납품 취소")
    assert (final["last_work"], final["work_date"]) == (log["text"], log["at"])


def test_import_preview_retains_missing_fields_and_accepts_only_observed_document_facts(client):
    file = _docx("견본 자색차", "실제 출시일: 2024-02-29", "용기 계약 종료", "다음 안은 출시 예정: 2025-03-01")
    fake = FakeLLM({"ideas_import": {"items": [
        {"name": "견본 자색차", "concept": "부드럽게 우린 자색차", "launched_on": "2024-02-29", "status": "단종",
         "reason": "용기 계약 종료"},
        {"name": "견본 다음 안", "launched_on": "2025-03-01", "reason": "만들어 낸 사유"},
        {"name": "견본 날짜 누락", "launched_on": "2024"},
    ]}})
    set_llm(fake)
    body = {"filename": "합성.docx", "content_base64": file}
    result = client.post(f"{ROOT}/import/preview", json=body).json()
    observed, plan, partial = result["items"]
    assert observed["row"]["launched_on"] == "2024-02-29" and observed["row"]["reason"] == "용기 계약 종료"
    assert observed["row"]["concept"] == "부드럽게 우린 자색차"
    assert plan["row"]["launched_on"] is None and plan["row"]["reason"] is None
    assert {"launched_on", "reason", "concept"} <= set(plan["missing"])
    assert partial["row"]["launched_on"] is None and "launched_on" in partial["missing"]
    assert not store.STORE_DIR.exists()
    assert [call["task"] for call in fake.calls] == ["ideas_import"]

    first = {"name": "견본 자색차", "status": "단종"}
    saved = client.post(f"{ROOT}/import/commit", json={"items": [first]}).json()["items"][0]
    assert saved["launched_on"] is None
    client.patch(f"{ROOT}/{saved['id']}", json={"concept": "검수자가 수정한 기획 설명"})
    batch = {"items": [observed["row"], first, observed["row"]]}
    committed = client.post(f"{ROOT}/import/commit", json=batch).json()["items"]
    assert len(committed) == 1 and committed[0]["id"] == saved["id"]
    assert committed[0]["launched_on"] == "2024-02-29" and committed[0]["concept"] == "검수자가 수정한 기획 설명"
    assert client.post(f"{ROOT}/import/commit", json=batch).json()["items"] == committed


def test_cases_returns_board_rows_and_resolves_verified_chat_evidence(client):
    chats.save({"id": "mock-chat", "note": {"confirmed": True, "concepts": [{
        "id": "mock-concept", "name": "견본 모과차", "brand": "새봄", "points": ["훈연한 모과 향"],
    }]}})
    chat_row = next(row for row in _by_id(client).values() if row["source"] == "chat")
    assert chat_row["concept"] == "훈연한 모과 향"
    completed = {"name": "견본 모과차", "brand": "새봄", "chat_id": "mock-chat", "status": "단종"}
    false_link = {"name": "견본 찻잎차", "brand": "새봄", "chat_id": "mock-chat", "status": "단종"}
    imported, other = client.post(f"{ROOT}/import/commit", json={"items": [completed, false_link]}).json()["items"]
    assert imported["chat_id"] == "mock-chat" and other["chat_id"] is None
    endpoint = f"{ROOT}/{imported['id']}"
    client.post(f"{endpoint}/logs", json={"key": str(uuid4()), "text": "도자기 전용 진열을 검토함"})
    items = client.get(f"{ROOT}/cases", params={"q": "도자기 전용"}).json()["items"]
    assert items == [_by_id(client)[imported["id"]]]
    assert items[0]["chat_id"] == "mock-chat" and "logs" not in items[0]
    assert client.get(f"{endpoint}/logs").json()["items"][0]["text"] == "도자기 전용 진열을 검토함"
    assert client.get(f"{ROOT}/cases", params={"q": "겹치지 않는 검색어"}).json() == {"items": []}


def test_saved_chat_decisions_need_a_dated_user_turn_and_a_named_concept(client, monkeypatch):
    concepts = [
        {"id": "base", "name": "견본 쑥차"},
        {"id": "light", "name": "견본 쑥차 라이트"},
    ]
    rec = {"id": "mock-decisions", "updated_at": "2026-06-01T12:00:00Z", "messages": [], "turns": [],
           "note": {"confirmed": True, "concepts": concepts}}

    def add_turn(text, at):
        n = len(rec["turns"]) + 1
        rec["messages"].extend([{"id": f"u{n}", "role": "user", "text": text},
                               {"id": f"reply{n}", "role": "assistant", "text": "견본 쑥차는 개발 중단 사유: 계약 해지"}])
        rec["turns"].append({"n": n, "message_id": f"reply{n}", "started_at": at})
        chats.save(rec)

    decision = "견본 쑥차 라이트는 용기 공급 취소로 개발을 중단했습니다."
    add_turn("원가 상승으로 개발을 중단했습니다.", "2026-06-02T01:00:00+00:00")
    add_turn(decision, "2026-06-02T02:00:00+00:00")
    add_turn("견본 쑥차는 유사 사례에서 개발을 중단했는지 알려줘", "2026-06-02T03:00:00+00:00")
    add_turn("견본 쑥차는 판매가 줄면 원가 문제로 개발을 중단합니다.", "2026-06-02T04:00:00+00:00")
    add_turn("견본 쑥차는 개발 중단을 제안합니다.", "2026-06-02T05:00:00+00:00")
    add_turn("견본 쑥차는 가격 인상 우려가 큽니다.", "2026-06-02T06:00:00+00:00")
    add_turn("견본 쑥차는 유통 계약 취소로 개발을 중단했습니다.", None)
    rows = {row["name"]: row for row in _by_id(client).values()}
    base, light = rows["견본 쑥차"], rows["견본 쑥차 라이트"]
    assert base["status"] == "기획 중" and base["last_work"] is None
    assert (light["status"], light["reason"], light["chat_id"]) == ("폐기", "용기 공급 취소", rec["id"])
    assert light["last_work"] == decision and light["work_date"] == "2026-06-02T02:00:00+00:00"
    endpoint = f"{ROOT}/{light['id']}"
    assert [log["text"] for log in client.get(f"{endpoint}/logs").json()["items"]] == [decision]
    assert chats.load(rec["id"])["messages"][2]["text"] == decision

    monkeypatch.setattr(store, "now", lambda: "2026-06-03T00:00:00+00:00")
    client.post(f"{endpoint}/logs", json={"key": str(uuid4()), "text": "견본 용기 견적을 확인함"})
    updated = _by_id(client)[light["id"]]
    assert updated["status"] == "폐기" and updated["last_work"] == "견본 용기 견적을 확인함"

    monkeypatch.setattr(store, "now", lambda: "2026-06-04T00:00:00+00:00")
    reopened = client.patch(endpoint, json={"status": "정성 조사 중", "reason": None}).json()
    assert reopened["status"] == "정성 조사 중" and reopened["reason"] is None
    assert _by_id(client)[light["id"]] == reopened

    later = "견본 쑥차 라이트는 진열할 공간이 부족해 개발을 중단하기로 최종 결정했습니다."
    add_turn(later, "2026-06-05T00:00:00+00:00")
    stopped = _by_id(client)[light["id"]]
    assert (stopped["status"], stopped["reason"], stopped["last_work"]) == ("폐기", "진열할 공간이 부족해", later)
    concepts[1].update(status="정량 조사 중", status_updated_at="2026-06-06T00:00:00+00:00")
    chats.save(rec)
    row = _by_id(client)[light["id"]]
    assert (row["status"], row["reason"]) == ("정량 조사 중", None)
    history = client.get(f"{endpoint}/logs").json()["items"]
    assert len(history) == 4
    assert history[0]["text"] == later and history[-1]["text"] == decision


def test_in_progress_user_turn_supplies_time_for_single_concept_decision(client):
    text = "이 제품은 귤 농축액 원가를 맞추지 못해 개발을 중단한다."
    rec = {"id": "mock-active", "messages": [{"id": "u1", "role": "user", "text": text}],
           "turns": [{"n": 1, "message_id": "pending-reply", "started_at": "2026-06-05T00:00:00Z"}],
           "note": {"confirmed": True, "concepts": [{"id": "one", "name": "견본 만다린차"}]}}
    chats.save(rec)
    row = next(iter(_by_id(client).values()))
    assert (row["status"], row["reason"], row["last_work"]) == ("폐기", "귤 농축액 원가를 맞추지 못해", text)
    assert store.stop_decision("귤 농축액 원가를 맞추지 못해 개발을 중단할 수도 있다.") is None


def test_starting_research_records_actual_work_only(client):
    row = _create(client)
    logs = f"{ROOT}/{row['id']}/logs"
    for note, status in [
        ("다음 주에 정성 인터뷰를 시작할까요?", "기획 중"),
        ("오늘부터 정성 인터뷰 시작했어요. 이번 조사는 제가 맡을게요.", "정성 조사 중"),
        ("정량 조사를 시작할 예정이에요.", "정성 조사 중"),
        ("정량 조사를 시작했습니다.", "정량 조사 중"),
    ]:
        assert client.post(logs, json={"key": str(uuid4()), "text": note}).is_success
        stored = _by_id(client)[row["id"]]
        assert (stored["status"], stored["last_work"], stored["owner"]) == (status, note, None)


def test_owner_follows_explicit_dated_chat_assignments_across_edits(client, monkeypatch):
    rec = {"id": "mock-owners", "messages": [], "note": {"confirmed": True, "concepts": [
        {"id": "one", "name": "견본 곡물차", "owner": "기존담당"},
        {"id": "two", "name": "견본 곡물차 라이트"},
    ]}}

    def say(day, text, role="user"):
        rec["messages"].append({"id": f"msg{len(rec['messages'])}", "role": role,
                                "text": text, "created_at": f"2026-06-{day:02}T09:00:00Z"})
        chats.save(rec)

    say(1, "담당자: 임가람")
    say(1, "견본 곡물차 라이트는 김하늘님이 담당합니다.", role="assistant")
    say(1, "견본 곡물차 라이트의 담당자를 김하늘로 변경할까요?")
    say(1, "견본 곡물차 라이트의 담당자는 후보입니다.")
    rows = {row["name"]: row for row in _by_id(client).values()}
    base_id, light_id = (rows[name]["id"] for name in ("견본 곡물차", "견본 곡물차 라이트"))
    endpoint = f"{ROOT}/{light_id}"
    assert rows["견본 곡물차"]["owner"] == "기존담당"
    assert rows["견본 곡물차 라이트"]["owner"] is None
    assert client.get(f"{endpoint}/logs").json()["items"] == []

    say(2, "견본 곡물차 라이트는 견적 미달로 개발을 중단했습니다.")
    assigned = "견본 곡물차 라이트의 담당자는 김하늘입니다."
    say(3, assigned)
    row = _by_id(client)[light_id]
    assert (row["owner"], row["status"], row["last_work"]) == ("김하늘", "폐기", assigned)
    assert _by_id(client)[base_id]["owner"] == "기존담당"
    assert [r["id"] for r in client.get(f"{ROOT}/cases", params={"q": "견적 미달"}).json()["items"]] == [light_id]
    assert client.get(f"{endpoint}/logs").json()["items"][0]["text"] == assigned

    monkeypatch.setattr(store, "now", lambda: "2026-06-04T08:00:00Z")
    assert client.patch(endpoint, json={"owner": "기존수정"}).json()["owner"] == "기존수정"
    say(5, "견본 곡물차 라이트 담당자를 윤가람으로 변경해줘.")
    monkeypatch.setattr(store, "now", lambda: "2026-06-06T08:00:00Z")
    assert client.patch(endpoint, json={"concept": "새로운 용기"}).json()["owner"] == "윤가람"
    say(7, "견본 곡물차 라이트 담당자: 미지정")
    row = _by_id(client)[light_id]
    assert row["owner"] is None and row["work_date"].startswith("2026-06-07")
    logs = client.get(f"{endpoint}/logs").json()["items"]
    assert len(logs) == len({log["id"] for log in logs})
    assert client.get(f"{endpoint}/logs").json()["items"] == logs


def test_single_confirmed_concept_accepts_an_explicit_owner_without_repeating_its_name(client):
    rec = {"id": "mock-one-owner", "note": {"confirmed": True, "concepts": [{"id": "one", "name": "견본 잎차"}]},
           "messages": [], "turns": []}
    for i, text in enumerate(["이 기획의 담당자를 임가람으로 해줘.", "제가 맡을게요.",
                              "예를 들어\n담당자: 다른사람", "담당자: tbd"], start=1):
        rec["messages"].append({"id": f"u{i}", "role": "user", "text": text, "at": f"2026-06-0{i}T09:00:00Z"})
    chats.save(rec)
    row, = _by_id(client).values()
    assert row["owner"] == "임가람" and row["last_work"] == rec["messages"][0]["text"]
    assert len(client.get(f"{ROOT}/{row['id']}/logs").json()["items"]) == 1

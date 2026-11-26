"""매대 방문 기록에 근거한 집단 인터뷰. 기존 시연은 마지막의 대본을 사용한다."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator
from contextvars import Context
from copy import deepcopy
from typing import BinaryIO, Literal

from llm.base import LLMError, get_llm
from shelftest import group_dialogue, group_setup, group_store, interview, result, runner, store

Session = dict
ROUNDS = {"fgi": 1, "fgd": 2}
ATTEMPTS = 3
_tasks: set[asyncio.Task] = set()
log = logging.getLogger(__name__)


def setup(run_id: str) -> dict | None:
    return group_setup.prepare(run_id)


def _existing_run(run_id: str) -> dict | None:
    if not isinstance(run_id, str) or not store.ID_RE.fullmatch(run_id):
        return None
    meta = store.load_meta(run_id)
    return meta if meta and meta.get("id") == run_id else None


def get_session(run_id: str, session_id: str) -> Session | None:
    record = group_store.read(run_id, session_id) if _existing_run(run_id) else None
    return record["session"] if record else None


def completed(run_id: str) -> list[Session]:
    return group_store.completed(run_id) if _existing_run(run_id) else []


def conclusions(run_id: str) -> dict | None:
    sessions = completed(run_id)
    if not sessions:
        return None
    session = sessions[-1]
    people = {p["id"]: p["who"] for p in session["participants"]}
    turns = {t["id"]: t for t in session["turns"]}
    relevant = [turn_id for findings in session["findings"].values() for f in findings for turn_id in f["turn_ids"]]
    quotes = []
    seen = set()
    for turn_id in dict.fromkeys([*relevant, *turns]):
        turn = turns[turn_id]
        if turn["person"] in seen:
            continue
        seen.add(turn["person"])
        quotes.append({"turn_id": turn_id, "person": turn["person"], "who": people[turn["person"]],
                       "text": turn["text"], "quote": turn["text"]})
        if len(quotes) == 3:
            break
    return {"question": session["question"], "mode": session["mode"], "session_id": session["id"],
            **session["findings"], "quotes": quotes}


async def _ask(record: dict, turn_id: str, visitor: interview.Visitor, participant: dict, names: set[str],
               own: list[dict], peers: list[dict]) -> dict | None:
    session = record["session"]
    question = {"id": session["question_id"], "text": session["question"]}
    data = group_dialogue.ask_data(visitor, participant, question, own, peers)
    attempts = record["attempts"]
    attempt = attempts.get(turn_id, {})
    if attempt.get("state") == "pending":
        # 처리 중 서버가 중단되면 이미 보낸 호출인지 알 수 없다. 같은 호출을 다시 보내지 않는다.
        return None
    for number in range(attempt.get("number", 0) + 1, ATTEMPTS + 1):
        if attempt.get("why"):
            data["retry"] = attempt["why"]
        llm = get_llm()
        user = json.dumps(data, ensure_ascii=False)
        attempts[turn_id] = {"number": number, "state": "pending"}
        session["calls"] += 1
        group_store.save(record)
        try:
            raw = await llm.ask("group_turn", group_dialogue.SYSTEM, user, group_dialogue.SCHEMA,
                                timeout=interview.TIMEOUT, model=runner.shopper_model())
        except LLMError:
            raw = None
        turn, why = (group_dialogue.checked(raw, visitor, participant, names, own, peers)
                     if isinstance(raw, dict) else (None, "답을 받지 못했어요"))
        if turn is not None:
            return turn
        attempt = {"number": number, "state": "failed", "why": why}
        attempts[turn_id] = attempt
        group_store.save(record)
    return None


async def _respond(record: dict, round_number: int, turn_id: str, visitor: interview.Visitor,
                   participant: dict, names: set[str], own: list[dict], peers: list[dict]) -> bool:
    turn = await _ask(record, turn_id, visitor, participant, names, own, peers)
    if turn is None:
        return False
    record["session"]["turns"].append({"id": turn_id, "person": visitor.visitor, "round": round_number, **turn})
    record["attempts"][turn_id]["state"] = "saved"
    group_store.save(record)
    return True


async def _run(record: dict, claim: BinaryIO) -> None:
    session = record["session"]
    run_id = record["run_id"]
    try:
        meta = _existing_run(run_id)
        participants = session["participants"]
        ids = [p["id"] for p in participants]
        pairs, _ = result.concept_visits(store.answers(run_id)) if meta else ([], set())
        visitors = interview.find_many(meta, pairs, ids) if meta else {}
        if len(visitors) != len(ids):
            session.update(status="error", error="일부 참석자의 매대 기록을 찾을 수 없어요.")
        else:
            info = group_setup.shelf_info(meta)
            names = {label for label, _ in info.values()} | {meta["concept"]["name"], *(p["choice"] for p in participants)}
            for number in range(1, session["rounds"] + 1):
                earlier = [t for t in session["turns"] if t["round"] < number]
                done = {t["person"] for t in session["turns"] if t["round"] == number}
                pending = []
                async with asyncio.TaskGroup() as tasks:
                    for index, participant in enumerate(participants, 1):
                        person = participant["id"]
                        if person in done:
                            continue
                        own = [t for t in earlier if t["person"] == person]
                        peers = [t for t in earlier if t["person"] != person and t["round"] == number - 1]
                        turn_id = f"{session['id']}-{number}-{index}"
                        pending.append(tasks.create_task(_respond(record, number, turn_id, visitors[person],
                                                                   participant, names, own, peers)))
                # 답을 확인하지 못한 참석자는 빼고 이어 간다(11-25): 한 명 때문에 인터뷰 전체를 버리지 않는다.
                # 첫 차례에 아무도 확인되지 않았을 때만 실패로 끝낸다. 뒤 차례가 비면 앞 차례까지로 맺는다.
                answered = {t["person"] for t in session["turns"] if t["round"] == number}
                if not answered:
                    if number == 1:
                        session.update(status="error", error="참석자의 답을 확인하지 못했어요.")
                    break
                participants = [p for p in participants if p["id"] in answered]
            if session["status"] != "error":
                session.update(status="done", findings=group_dialogue.findings(session["turns"]))
        record["finished_at"] = time.time_ns()
        group_store.save(record)
    except Exception:
        log.exception("집단 인터뷰를 진행하지 못함")
        session.update(status="error", error="인터뷰를 마치지 못했어요. 확인한 발언만 남겼어요.")
        group_store.save(record)
    finally:
        claim.close()


def _start(record: dict, claim: BinaryIO) -> None:
    task = asyncio.create_task(_run(record, claim), context=Context())
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


async def discuss(run_id: str, question_id: str, mode: str, visitor_ids: list[str]) -> AsyncIterator[Session]:
    """같은 질문·방식·참석자는 같은 기록을 열고, 확인된 답을 한 발언씩 내보낸다."""
    if not _existing_run(run_id) or not isinstance(question_id, str) or not isinstance(mode, str) or mode not in ROUNDS:
        return
    if (not 2 <= len(visitor_ids) <= group_setup.MAX_PARTICIPANTS
            or not all(isinstance(v, str) for v in visitor_ids) or len(set(visitor_ids)) != len(visitor_ids)):
        return
    session_id = group_store.session_id(run_id, question_id, mode, visitor_ids)
    record = group_store.read(run_id, session_id)
    if record is None:
        payload = setup(run_id)
        if payload is None:
            return
        question = group_setup.resolve_question(payload, question_id)
        participants = {p["id"]: p for p in payload["candidates"]}
        if question is None or any(v not in participants for v in visitor_ids):
            return
        session = {"id": session_id, "mode": mode, "question_id": question_id, "question": question["text"],
                   "participants": [participants[v] for v in visitor_ids], "rounds": ROUNDS[mode],
                   "status": "running", "turns": [], "findings": {"agreed": [], "split": [], "changed": []}, "calls": 0}
        record = {"run_id": run_id, "session": session, "attempts": {}}
    claim = group_store.claim(run_id, session_id)
    if claim is not None:
        try:
            saved = group_store.read(run_id, session_id)
            if saved is None:
                group_store.save(record)
            else:
                record = saved
            if record["session"]["status"] == "running":
                _start(record, claim)
                claim = None
        finally:
            if claim is not None:
                claim.close()
    else:
        record = group_store.read(run_id, session_id) or record

    current = deepcopy(record["session"])
    yield current
    while current["status"] == "running":
        await asyncio.sleep(0.025)
        saved = group_store.read(run_id, session_id)
        if saved is None:
            yield {**current, "status": "error", "error": "인터뷰 기록을 읽지 못했어요."}
            return
        latest = saved["session"]
        for length in range(len(current["turns"]) + 1, len(latest["turns"]) + 1):
            yield {**current, "turns": latest["turns"][:length], "calls": latest["calls"]}
        current = latest
        if current["status"] != "running":
            yield current
        elif (claim := group_store.claim(run_id, session_id)) is not None:
            # 다른 요청 또는 프로세스가 남긴 기록도 잠금이 풀리면 이어받는다.
            fresh = group_store.read(run_id, session_id)
            if fresh and fresh["session"]["status"] == "running":
                _start(fresh, claim)
            else:
                claim.close()

Topic = Literal["form", "price", "flavor"]

_PARTICIPANTS = (
    ("p1", "24세 여성, 대학생", "밀키스 화채", True),
    ("p2", "32세 여성, 사무직", "보리차", False),
    ("p3", "44세 남성, 현장직", "콜라", False),
    ("p4", "28세 남성, 디자이너", "밀키스 화채", True),
    ("p5", "36세 여성, 매장 직원", "플레인 탄산수", False),
    ("p6", "51세 남성, 자영업", "밀키스 오리지널", False),
)


def _turn(mode: str, person: str, round_number: int, topic: Topic, text: str,
          reply_to: str | None = None) -> dict:
    turn = {"id": f"{mode}-{round_number}-{person}", "person": person, "round": round_number,
            "topic": topic, "text": text}
    if reply_to is not None:
        turn["replyTo"] = f"{mode}-1-{reply_to}"
    return turn


def demo_sessions() -> dict:
    """선택 기록을 공유하는 FGI·FGD 시연용 자료를 매번 새로 구성한다."""
    fgi = [
        _turn("fgi", "p1", 1, "flavor", "수업 끝나고 친구랑 간식을 먹을 거라 밀키스 화채를 골랐어요. 여름에만 나오는 수박화채 맛이라 같이 얘깃거리가 될 것 같았어요."),
        _turn("fgi", "p2", 1, "form", "점심 식사에 곁들일 거라 보리차를 골랐어요. 화채 맛은 궁금한데 점심에 곁들일 거라면 탄산 없는 쪽을 먼저 볼 것 같아요."),
        _turn("fgi", "p3", 1, "price", "일하다 쉬는 시간에 마실 거라 늘 집는 콜라를 골랐어요. 처음 보는 맛에 1,800원을 쓰기엔 망설여져요."),
        _turn("fgi", "p4", 1, "price", "퇴근길엔 가끔 새로운 음료를 골라요. 오늘은 1,800원이면 제 예산 안이라 밀키스 화채를 집었어요."),
        _turn("fgi", "p5", 1, "form", "퇴근하고 걸으면서 마시려고 플레인 탄산수를 집었어요. 그럴 땐 과일 맛보다 단맛 없는 탄산이 먼저 생각나요."),
        _turn("fgi", "p6", 1, "flavor", "집에 가져가 가족이랑 나눌 거라 밀키스 오리지널을 골랐어요. 수박화채 향이 은은하다고 써 있으면 가족이랑 마실 때도 고려해 볼래요."),
    ]
    fgd = [
        _turn("fgd", "p1", 1, "flavor", "수업 끝나고 친구랑 간식 먹을 때 나눌 거라 밀키스 화채를 골랐어요. 수박화채 맛이라 여름 한정이라는 말이 잘 어울렸어요."),
        _turn("fgd", "p2", 1, "form", "점심에 마실 거라 보리차로 갔어요. 화채가 궁금하긴 한데 점심엔 탄산이 없는 쪽이 편해요."),
        _turn("fgd", "p3", 1, "price", "일하다 잠깐 쉬는 거라 늘 사는 콜라를 집었어요. 처음 보는 제품에 1,800원은 망설여져요."),
        _turn("fgd", "p4", 1, "price", "퇴근길에 평소랑 다른 걸 집고 싶어서 밀키스 화채를 골랐어요. 새 음료에 1,800원 정도면 써요."),
        _turn("fgd", "p5", 1, "form", "퇴근하고 걸으면서 마실 거라 플레인 탄산수를 골랐어요. 저라면 화채 음료에도 탄산이 있어야 손이 갈 것 같아요."),
        _turn("fgd", "p6", 1, "flavor", "가족이랑 나눠 마실 거라 익숙한 밀키스 오리지널로 골랐어요. 수박화채 맛은 가족이 다 좋아할지 모르겠어요."),
        _turn("fgd", "p1", 2, "flavor", "가족이랑 마실 때는 익숙한 맛을 고를 것 같아요. 친구랑 간식 먹을 땐 수박화채처럼 계절이 드러나는 맛이 더 끌려요.", "p6"),
        _turn("fgd", "p2", 2, "form", "걸으면서 마실 때 탄산이 당긴다는 건 이해돼요. 밥이랑 먹을 거라면 화채 맛은 그대로 두고 탄산만 뺀 게 있을 때 비교해 볼래요.", "p5"),
        _turn("fgd", "p3", 2, "price", "퇴근길에 새 맛을 찾는 날이라면 1,800원을 낼 수도 있겠네요. 저는 일하다 쉴 때라 1,700원 정도면 콜라 옆에서 한 번 더 볼 것 같아요.", "p4"),
        _turn("fgd", "p4", 2, "price", "처음 보는 맛에 돈 쓰기 망설여진다는 건 공감해요. 저도 1,900원이면 같은 퇴근길이라도 평소 고르던 음료랑 가격부터 비교할 것 같아요.", "p3"),
        _turn("fgd", "p5", 2, "form", "아까는 화채에도 탄산이 있어야 한다고 했는데, 점심 얘기를 들으니 달라졌어요. 걸어갈 땐 탄산수를 고르겠지만 밥이랑 먹는다면 탄산 없는 화채도 살펴볼래요.", "p2"),
        _turn("fgd", "p6", 2, "flavor", "친구끼리 여름 간식으로 고른다면 수박화채 맛이 눈에 띄겠네요. 저는 오늘 가족이랑 나눌 거라 오리지널을 골랐지만, 수박향을 은은하게 한 안이 있으면 살펴볼래요.", "p1"),
    ]
    return {
        "participants": [{"id": person, "label": label, "choice": choice, "picked": picked}
                         for person, label, choice, picked in _PARTICIPANTS],
        "modes": {
            "fgi": {
                "question": "같은 질문을 한 명씩 드려요. 다른 참석자의 답은 보이지 않아요. 오늘 매대에서 무엇을 골랐고 무엇이 선택을 가른 이유였나요?",
                "turns": fgi,
                "summary": [
                    {"title": "맛과 음용 상황", "text": "친구와 나누는 여름 간식엔 수박화채 맛이 눈에 띄고, 가족과 나눌 때는 익숙한 맛을 골랐어요.",
                     "turnIds": ["fgi-1-p1", "fgi-1-p6"]},
                    {"title": "고르는 가격", "text": "퇴근길에 새 음료를 찾는 손님은 1,800원에 골랐고, 일하다 쉬는 손님은 같은 가격에서 콜라를 골랐어요.",
                     "turnIds": ["fgi-1-p3", "fgi-1-p4"]},
                    {"title": "탄산을 고르는 때", "text": "점심과 함께 마시는 손님은 보리차를, 퇴근길에 걷는 손님은 단맛 없는 탄산수를 골랐어요.",
                     "turnIds": ["fgi-1-p2", "fgi-1-p5"]},
                ],
            },
            "fgd": {
                "question": "매대에서 왜 그렇게 고르셨나요? 1차에는 각자 선택 이유를 답하고, 2차에는 앞 발언을 보고 동의하거나 다른 생각을 말해요.",
                "turns": fgd,
                "summary": [
                    {"title": "모인 의견", "text": "두 사람이 친구와 나누는 여름 간식이라면 수박화채 맛이 눈에 띈다고 했어요. 가족과 나누는 상황에서는 익숙한 맛이 남았어요.",
                     "turnIds": ["fgd-2-p1", "fgd-2-p6"]},
                    {"title": "갈린 의견", "text": "퇴근길에 새 음료를 찾는 손님은 1,800원이 괜찮았고, 일하다 쉬는 손님은 더 낮은 가격에서 다시 비교하겠다고 했어요.",
                     "turnIds": ["fgd-1-p3", "fgd-1-p4", "fgd-2-p3"]},
                    {"title": "토론 중 바뀐 생각", "text": "화채에도 탄산이 있어야 한다던 손님이 다른 참석자의 점심 상황을 듣고, 식사 때라면 탄산 없는 화채도 살펴보겠다고 했어요.",
                     "turnIds": ["fgd-1-p5", "fgd-1-p2", "fgd-2-p5"]},
                ],
            },
        },
    }

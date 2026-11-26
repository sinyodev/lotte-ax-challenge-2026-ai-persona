"""읽기(agent/steps.py read)를 진짜 모델로 잰다. pytest가 아니다. 손으로 돌린다 (지시서 09의 5절).

    cd app/server && AX_LLM=cli uv run python evals/read_live.py            # 모두(모델 호출 약 서른다섯 번)
    cd app/server && AX_LLM=cli uv run python evals/read_live.py --only 1 3  # 몇 개만

기획자의 말 서른다섯 개(할 일마다 둘 이상, 참가자가 실제로 한 말 넷 포함. 지시서 11의 넓은 말 다섯)를 네 가지 노트 위에서 읽게 하고,
읽기가 고른 할 일을 기대와 견준다.
- 기대: 꼭 골라야 하는 일(required)과 골라도 되는 일(allowed). required의 "a|b"는 둘 중 하나면 된다.
- 맞음: required를 모두 고르고, required와 allowed 밖의 일을 고르지 않았다.
- 도구 재현율 = 고른 것 가운데 required에 든 수 / required의 수(모두 더해서)
- 도구 정밀도 = 고른 것 가운데 required나 allowed에 든 수 / 고른 수(모두 더해서)
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent import machine, steps  # noqa: E402
from agent.note import Note, Slot  # noqa: E402
from tools import consumer  # noqa: E402
from tools.consumer import Group  # noqa: E402


def _idea(i: str, name: str, flavor: str, pack: str, features: list[str], line: str, by: str = "chilseong") -> dict:
    c, v = pack.split()
    return {"id": i, "name": name, "flavor": flavor, "pack": pack, "features": features, "line": line, "diff": "",
            "by": by, "_container": c, "_volume": int(v.removesuffix("ml"))}


def note_empty() -> Note:
    return Note()


def note_product() -> Note:
    n = Note(product=Slot("제로 탄산", "planner"), kind="탄산음료(저칼로리)", shelf_kind="탄산")
    n.evidence = [{"id": "ev-1", "origin": "record", "text": "제로 탄산은 다른 음료보다 20대 4.5배, 30대 2.4배 자주 마셔요",
                   "source": "2024 국민건강영양조사 식품섭취조사, 음용 사례 20대 126건, 30대 74건"}]
    n.last_say = ("제로 탄산으로 기획해 볼게요. 국민건강영양조사를 찾아보니 제로 탄산은 20대가 다른 음료보다 네 배 넘게 자주 "
                  "마시더라고요. 20대 쪽으로 아이디어를 내 볼까요?")
    n.last_offer = machine._actions(n, "next-step", [("ideas", "아이디어 내기"), ("target:all|19-29", "타깃을 20대로 하기")])
    return n


def note_ideas() -> Note:
    n = note_product()
    n.target, n.group = Slot("20대", "chilseong"), Group(age="19-29", label="20대")
    n.occasion, n.occasion_code = Slot("집에서 식사할 때 입가심", "chilseong"), "D8"
    n.need = Slot("기름진 저녁을 당 걱정 없이 개운하게", "chilseong")
    n.thoughts = ["아침 밥 먹을 때 마시는 탄산"]
    n.ideas = [
        _idea("a", "유자 제로 스파클링", "유자", "페트 500ml", ["제로 칼로리", "유자 과즙 향"], "아침 밥상에 상큼한 한 모금"),
        _idea("b", "보리 제로 소다", "볶은 보리", "캔 355ml", ["제로 칼로리", "구수한 보리 향"], "밥과 어울리는 구수한 탄산"),
        _idea("c", "유자 생강 탄산", "유자와 생강", "캔 250ml", ["제로 칼로리", "생강의 알싸함"], "속을 깨우는 알싸한 아침", "planner"),
    ]
    n.idea_seq = 3
    n.last_say = "아침 쪽으로 아이디어를 새로 내 봤어요. 마음에 드는 건 남기고, 컨셉으로 만들 걸 말씀해 주세요."
    n.last_offer = machine._actions(n, "idea-board", [("make-concepts", "컨셉으로 만들기"), ("more-ideas", "다른 아이디어 보기")])
    return n


def note_concepts() -> Note:
    n = note_ideas()
    n.stage = "concept"
    n.concepts = [
        {"id": "a", "name": "아침 유자 스파클", "headline": "아침을 깨우는 상큼한 한 모금", "pack": "500ml 페트",
         "price": "2,300원", "_container": "페트", "_volume": 500},
        {"id": "c", "name": "유자 생강 모닝 탄산", "headline": "속까지 개운한 아침", "pack": "250ml 캔",
         "price": "1,700원", "_container": "캔", "_volume": 250},
    ]
    n.last_say = "두 개 다 컨셉 보드로 만들었어요. 가격은 편의점에서 비슷한 제품이 팔리는 값에 맞췄어요. 고칠 데 있으면 말씀해 주세요."
    n.last_offer = machine._actions(n, "concept-board", [("confirm-concepts", "이 컨셉으로 확정하기"),
                                                          ("more-ideas", "다른 아이디어 보기")])
    return n


NOTES = {"빈 노트": note_empty, "제품만": note_product, "아이디어 보드": note_ideas, "컨셉 보드": note_concepts}

# (노트, 기획자의 말, 꼭 골라야 하는 일, 골라도 되는 일)
CASES: list[tuple[str, str, set[str], set[str]]] = [
    ("빈 노트", "제로 탄산 신제품 하나 검토해 보고 싶어", {"note"}, {"thought"}),
    ("제품만", "20대", {"note"}, {"ideas", "thought"}),
    ("아이디어 보드", "타깃을 30대로 바꾸자", {"note"}, {"ideas"}),
    ("제품만", "아침용", {"thought"}, {"note", "ideas"}),
    ("아이디어 보드", "밥 먹을때면 아침용 탄산", {"thought"}, {"note", "ideas"}),
    ("제품만", "아이디어 줘", {"ideas"}, set()),
    ("아이디어 보드", "아침의 컨셉이 더 강한 아이디어를 줘볼래?", {"ideas"}, {"more"}),  # 요청은 생각이 아니다(지시서 11)
    ("제품만", "다른 아이디어는 없어?", {"ideas"}, {"more"}),
    ("아이디어 보드", "다른 아이디어는 없어?", {"more"}, {"ideas"}),
    ("아이디어 보드", "다른 건 없어?", {"more"}, {"ideas"}),
    ("아이디어 보드", "B는 맛을 유자로", {"edit_idea"}, {"thought"}),
    ("아이디어 보드", "첫 번째는 좋은데 맛을 자몽으로 바꿔 줘", {"edit_idea"}, {"keep", "thought"}),
    ("아이디어 보드", "내 생각은 매실 탄산이야", {"my_idea"}, {"thought"}),
    ("아이디어 보드", "내 아이디어로 레몬 생강 탄산 넣어 줘", {"my_idea"}, {"thought"}),
    ("아이디어 보드", "B는 남겨 줘", {"keep"}, set()),
    ("아이디어 보드", "두 번째 거 괜찮다, 그건 남기자", {"keep"}, set()),
    ("아이디어 보드", "B는 빼 줘", {"drop"}, set()),
    ("아이디어 보드", "두 번째는 빼고 내 아이디어로 레몬 생강 탄산 넣어 줘", {"drop", "my_idea"}, {"thought"}),
    ("아이디어 보드", "A랑 C로 컨셉 만들자", {"concepts"}, set()),
    ("아이디어 보드", "유자 들어간 두 개로 컨셉 만들자", {"concepts"}, set()),
    ("컨셉 보드", "헤드라인이 약해", {"edit_concept"}, set()),
    ("컨셉 보드", "첫 번째 컨셉 용량을 250으로 줄이고 가격은 1,500원으로", {"edit_concept"}, set()),
    ("아이디어 보드", "왜 20대야?", {"answer"}, set()),
    ("컨셉 보드", "이 숫자 어디서 나왔어?", {"answer"}, set()),
    ("컨셉 보드", "이대로 확정", {"confirm"}, set()),
    ("컨셉 보드", "좋아, 이걸로 정할게", {"confirm"}, set()),
    ("컨셉 보드", "매대에 올려서 테스트해 봐", {"shelf_test"}, set()),
    ("컨셉 보드", "첫 번째 컨셉으로 매대 테스트해 줘", {"shelf_test"}, set()),
    ("컨셉 보드", "테스트 결과 보여 줘", {"shelf_result"}, set()),
    ("컨셉 보드", "몇 명이나 집었어?", {"shelf_result"}, {"answer"}),
    ("컨셉 보드", "가격 낮춰서 다시 돌려 봐", {"improve_run"}, {"edit_concept"}),
    ("컨셉 보드", "1,500원으로 해서 다시 물어봐", {"improve_run"}, {"edit_concept"}),
    ("컨셉 보드", "개선안 만들어 줘", {"improve"}, set()),
    ("컨셉 보드", "고친 안은 어땠어?", {"improve_result"}, set()),
    ("컨셉 보드", "결과 보고서 만들어 줘", {"report"}, {"download"}),
    ("컨셉 보드", "컨셉 보드 파일로 내려받고 싶어", {"download"}, set()),
    ("컨셉 보드", "보고서로 뽑아 줘", {"download"}, set()),
    ("빈 노트", "중고차 시세 좀 알려줘", {"out_of_scope"}, set()),
    ("제품만", "오늘 점심 뭐 먹지?", {"out_of_scope"}, set()),
    # 지시서 11의 3절: 넓은 말도 출발점이다("a|b"는 둘 중 하나를 고르면 된다)
    ("빈 노트", "음 건강음료쪽?", {"note|thought"}, {"note", "thought", "ideas"}),
    ("빈 노트", "아침에 마시는 거", {"note|thought"}, {"note", "thought", "ideas"}),
    ("빈 노트", "20대 여성이 좋아할 만한 거 없을까", {"note|thought"}, {"note", "thought", "ideas", "recommend"}),
    ("빈 노트", "요즘 뜨는 걸로", {"recommend|thought"}, {"thought", "ideas", "recommend"}),
    ("빈 노트", "뭐 할 수 있어?", {"answer"}, set()),
]


def _flat(required: set[str]) -> set[str]:
    return {a for r in required for a in r.split("|")}


def _hit(r: str, picked: list[str]) -> bool:
    return any(a in picked for a in r.split("|"))


async def one(k: int, sem: asyncio.Semaphore) -> dict:
    where, text, required, allowed = CASES[k - 1]
    note = NOTES[where]()
    async with sem:
        started = time.monotonic()
        try:
            r = await steps.read(machine._read_context(note), text, list(consumer.all_occasions().values()))
            picked = [t.do for t in r.tasks]
            detail = "; ".join(f"{t.do}{'(' + t.slot + '=' + t.value + ')' if t.slot else ''}"
                               f"{' ids=' + ','.join(t.ids) if t.ids else ''}{' text=' + t.text if t.text else ''}"
                               for t in r.tasks)
            looks = ", ".join(f"{lk.tool}{'(' + lk.arg + ')' if lk.arg else ''}" for lk in r.lookups)
        except steps.StepFailed as e:
            picked, detail, looks = [], f"실패: {e.why}", ""
        sec = round(time.monotonic() - started, 1)
    ok = all(any(a in picked for a in r.split("|")) for r in required) and set(picked) <= (_flat(required) | allowed)
    return {"k": k, "where": where, "text": text, "required": sorted(required), "allowed": sorted(allowed),
            "picked": picked, "detail": detail, "lookups": looks, "ok": ok, "sec": sec}


async def main(only: list[int], parallel: int) -> None:
    sem = asyncio.Semaphore(parallel)
    ks = only or list(range(1, len(CASES) + 1))
    rows = await asyncio.gather(*(one(k, sem) for k in ks))
    req_total = req_hit = picked_total = picked_ok = 0
    for r in rows:
        req, allowed, picked = set(r["required"]), set(r["allowed"]), r["picked"]
        req_total += len(req)
        req_hit += sum(1 for x in req if _hit(x, picked))
        picked_total += len(picked)
        picked_ok += sum(1 for p in picked if p in _flat(req) | allowed)
        mark = "맞음" if r["ok"] else "틀림"
        print(f"{r['k']:>2}. [{mark}] ({r['where']}) \"{r['text']}\" 기대 {'+'.join(r['required'])}"
              f"{' (허용 ' + ','.join(r['allowed']) + ')' if r['allowed'] else ''} → {r['detail']} | 찾기: {r['lookups'] or '-'} | {r['sec']}초")
    n_ok = sum(r["ok"] for r in rows)
    print(f"\n맞은 수: {n_ok}/{len(rows)}")
    print(f"도구 재현율: {req_hit}/{req_total} = {req_hit / max(1, req_total):.2f}")
    print(f"도구 정밀도: {picked_ok}/{picked_total} = {picked_ok / max(1, picked_total):.2f}")
    print("틀린 것: " + (", ".join(str(r["k"]) for r in rows if not r["ok"]) or "없음"))
    print(f"읽기의 모델: {steps.fast_model()}, 평균 {sum(r['sec'] for r in rows) / max(1, len(rows)):.1f}초")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", type=int, nargs="*", default=[])
    ap.add_argument("--parallel", type=int, default=3)
    args = ap.parse_args()
    os.environ.setdefault("AX_LLM", "cli")
    asyncio.run(main(args.only, args.parallel))

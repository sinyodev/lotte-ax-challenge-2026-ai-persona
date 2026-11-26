"""pytest 전체의 약속: 모델을 부르지 않는다(fake 어댑터만). 기존 재생 테스트는 AX_AGENT=replay로 돈다."""

from __future__ import annotations

import pytest

from agent import machine
from llm.base import set_llm


@pytest.fixture(autouse=True)
def _no_real_model(monkeypatch, tmp_path):
    monkeypatch.setenv("AX_LLM", "fake")
    monkeypatch.setenv("AX_AGENT", "replay")
    monkeypatch.setenv("AX_ONSITE_DIR", str(tmp_path / "onsite"))
    # 아침 트렌드 발행 일정은 시험에서 돌리지 않는다(바깥 사이트를 부르지 않게). 일정의 시험은 스스로 켠다
    monkeypatch.setenv("AX_TREND_SCHEDULE", "0")
    # 웹 검색 결과를 저장하는 곳을 시험마다 비운다(저장해 둔 진짜 결과를 쓰지 않는다)
    from tools import web

    monkeypatch.setattr(web, "CACHE_DIR", tmp_path / "web")
    # 대화를 저장하는 곳도 시험마다 따로 둔다(참가자의 대화 파일을 건드리지 않는다)
    import chats

    monkeypatch.setattr(chats, "STORE_DIR", tmp_path / "chats")
    # 매대 테스트의 파일도 시험마다 따로 둔다(지시서 15)
    from shelftest import runner, store as run_store

    monkeypatch.setattr(run_store, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(run_store, "BASE_DIR", tmp_path / "baselines")
    for task in list(runner.TASKS.values()):
        task.cancel()
    runner.TASKS.clear()
    chats.ACTIVE.clear()
    chats.DELETED.clear()
    set_llm(None)
    machine.reset()
    yield
    set_llm(None)
    machine.reset()

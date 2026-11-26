"""HTTP 응답의 수명, 대화 차례의 수명, 명시적인 멈춤을 따로 확인한다."""

import asyncio

import httpx

import chats
import main
from agent import machine
from events import Say, Stage
from llm import usage
from llm.base import note_call


def request(chat_id):
    return main.ChatRequest(id=chat_id, messages=[{"id": "u1", "role": "user", "content": chat_id}])


def test_leave_reopen_and_run_two_chats(monkeypatch):
    monkeypatch.setenv("AX_AGENT", "live")

    async def scenario():
        entered = {key: asyncio.Event() for key in ("a", "b")}
        release = asyncio.Event()

        async def gated(chat_id, *args, **kwargs):
            yield Stage(current="idea")
            note_call({"task": chat_id})
            entered[chat_id].set()
            await release.wait()
            usage.record({"model": "fake", "task": chat_id, "sec": 0, "ok": True},
                         system="", user="", output="")
            yield Say(text=chat_id)

        monkeypatch.setattr(machine, "turn", gated)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://test") as client:
            for chat_id in entered:
                response = await main.chat(request(chat_id))
                stream = response.body_iterator
                await anext(stream)
                await stream.aclose()  # 응답을 버려도 생산자는 계속 돈다.
                await asyncio.wait_for(entered[chat_id].wait(), 2)
            duplicate = await client.post("/api/chat", json=request("a").model_dump())
            assert duplicate.status_code == 409
            rows = (await client.get("/api/chats")).json()
            assert {row["id"]: row["status"] for row in rows} == {"a": "working", "b": "working"}
            partial = (await client.get("/api/chats/a")).json()
            assert partial["working"] and len(partial["messages"]) == 2
            last = partial["messages"][-1]
            assert last["parts"][-1]["type"] == "data-stage"
            tasks = [turn.task for turn in chats.ACTIVE.values()]
            release.set()
            await asyncio.wait_for(asyncio.gather(*tasks), 2)
            for chat_id in entered:
                saved = (await client.get(f"/api/chats/{chat_id}")).json()
                assert not saved["working"] and saved["status"] == "idle"
                message = saved["messages"][-1]
                assert message["parts"][-1]["text"] == chat_id
                record = chats.load(chat_id)["turns"]
                assert len(record) == 1 and not record[0]["stopped"]
                assert record[0]["usage"]["calls"] == 1 and record[0]["calls"] == [{"task": chat_id}]
                if chat_id == "a":
                    assert message["id"] == last["id"] and message["parts"][:-1] == last["parts"]

    asyncio.run(scenario())


def test_stop_is_idempotent_and_restores_note(monkeypatch):
    monkeypatch.setenv("AX_AGENT", "live")

    async def scenario():
        started = asyncio.Event()

        async def gated(chat_id, *args, **kwargs):
            machine.CONVS[chat_id].thoughts.append("미완성")
            yield Stage(current="idea")
            started.set()
            await asyncio.Event().wait()

        machine.adopt("stop", machine.Note())
        monkeypatch.setattr(machine, "turn", gated)
        response = await main.chat(request("stop"))
        await asyncio.wait_for(started.wait(), 2)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://test") as client:
            for _ in range(2):
                assert (await client.post("/api/chats/stop/stop")).status_code == 200
            assert (await client.post("/api/chats/missing/stop")).status_code == 200
            saved = (await client.get("/api/chats/stop")).json()
            assert not saved["working"] and saved["messages"][-1]["metadata"]["stopped"]
            assert machine.CONVS["stop"].thoughts == [] and chats.load("stop")["note"]["thoughts"] == []
            assert len(chats.load("stop")["turns"]) == 1
        assert '"stopped": true' in "".join([chunk async for chunk in response.body_iterator])

    asyncio.run(scenario())


def test_immediate_stop_and_shutdown():
    async def scenario():
        await main.chat(request("early"))
        await main.stop_chat("early")  # 작업이 처음 실행되기 전의 멈춤
        before = chats.load("early")
        assert before["messages"][-1]["stopped"]
        async with main.app.router.lifespan_context(main.app):
            await main.chat(request("early"))
            await main.chat(request("new"))
            await asyncio.sleep(0)
        assert not chats.ACTIVE and chats.load("early") == before and chats.load("new") is None

    asyncio.run(scenario())

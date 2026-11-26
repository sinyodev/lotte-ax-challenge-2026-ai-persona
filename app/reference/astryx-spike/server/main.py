import asyncio, json
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

app = FastAPI()

def sse(part): return f"data: {json.dumps(part, ensure_ascii=False)}\n\n"

@app.post("/api/chat")
async def chat(request: Request):
    body = await request.json()
    turn = sum(1 for m in body.get("messages", []) if m.get("role") == "user")
    async def gen():
        yield sse({"type": "start", "messageId": f"m{turn}"})
        yield sse({"type": "start-step"})
        text = ("세븐일레븐 음료 매대부터 봤어요. 제로 탄산이 9개인데 500ml 페트는 하나뿐이에요. 타깃에 따라 아이디어가 달라져서요. 누구를 먼저 볼까요?"
                if turn == 1 else "20대 직장인으로 볼게요. 기획 브리프에 적어 뒀어요.")
        yield sse({"type": "text-start", "id": "t1"})
        for ch in text:
            yield sse({"type": "text-delta", "id": "t1", "delta": ch}); await asyncio.sleep(0.01)
        yield sse({"type": "text-end", "id": "t1"})
        if turn == 1:
            q = {"questions": [{"kind": "single", "title": "누구를 먼저 볼까요?", "options": [
                {"id": "a", "label": "20대 직장인", "description": "당을 신경 쓰는 사람이 많아요"},
                {"id": "b", "label": "30~40대 직장인", "description": "오후에 가장 많이 마셔요"}]}]}
            yield sse({"type": "tool-input-available", "toolCallId": "q1", "toolName": "Question", "input": q})
        else:
            b = {"제품": "제로 탄산", "채널": "세븐일레븐 음료 매대", "타깃": "20대 직장인"}
            yield sse({"type": "tool-input-available", "toolCallId": "b1", "toolName": "show_brief", "input": b})
            yield sse({"type": "tool-output-available", "toolCallId": "b1", "output": {"ok": True}})
            yield sse({"type": "data-workbench", "data": {"card": "brief", "filled": 3}})
        yield sse({"type": "finish-step"})
        yield sse({"type": "finish"})
        yield "data: [DONE]\n\n"
    return StreamingResponse(gen(), media_type="text/event-stream", headers={"x-vercel-ai-ui-message-stream": "v1"})

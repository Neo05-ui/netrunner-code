"""capri-core: the local server.

Binds to 127.0.0.1 only. Nothing is exposed to the network.

Why this exists: a long-lived process keeps one conversation alive, so Ollama's
prompt-prefix cache stays warm. Measured on this machine, that is the
difference between ~45s and ~9s per turn. It is also the socket the Electron
body will talk to in Phase 5.

Events over the WebSocket, matching the blueprint:
  in :  {"type":"user_text","text":...}
  out:  {"type":"state","state":"thinking"|"idle"}
        {"type":"reply","text":...,"emotion":...,"latency_ms":...}
"""
from __future__ import annotations
import asyncio, json

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from .orchestrator import Capri

app = FastAPI(title="capri-core", docs_url=None, redoc_url=None)
bot = Capri()
_lock = asyncio.Lock()          # one turn at a time; CPU inference is serial anyway


class Ask(BaseModel):
    text: str


@app.get("/health")
async def health():
    return bot.health()


@app.post("/chat")
async def chat(ask: Ask):
    async with _lock:
        reply = await asyncio.to_thread(bot.turn, ask.text)
    return {"text": reply}


@app.post("/reset")
async def reset():
    """Clears the working window only. Durable memory is untouched —
    that is the whole point of it."""
    bot.history.clear()
    return {"ok": True, "history": 0}


@app.get("/memory")
async def memory():
    return {"facts": bot.facts.bullets(), **bot.store.stats()}


class Query(BaseModel):
    text: str
    k: int = 5


@app.post("/recall")
async def recall(q: Query):
    """Inspection endpoint: shows what recall would inject, and the scores."""
    hits = await asyncio.to_thread(bot.store.recall, q.text, q.k, 0.0)
    return {"hits": hits}


@app.websocket("/ws")
async def ws(sock: WebSocket):
    await sock.accept()
    try:
        while True:
            raw = await sock.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                msg = {"type": "user_text", "text": raw}

            if msg.get("type") != "user_text":
                continue

            await sock.send_json({"type": "state", "state": "thinking"})
            async with _lock:
                reply = await asyncio.to_thread(bot.turn, msg.get("text", ""))
            await sock.send_json({"type": "reply", "text": reply, "emotion": "idle"})
            await sock.send_json({"type": "state", "state": "idle"})
    except WebSocketDisconnect:
        pass


def main():
    import uvicorn
    cfg = bot.cfg.get("server", {})
    uvicorn.run(app, host="127.0.0.1", port=cfg.get("port", 8787), log_level="warning")


if __name__ == "__main__":
    main()

"""CloudBite demo API (FastAPI). Run:  uvicorn app:app --reload   then open http://localhost:8000"""
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel

import logic

app = FastAPI(title="CloudBite - Cancelled-order rescue demo")
INDEX = Path(__file__).with_name("index.html")


class OrderIn(BaseModel):
    user_id: int
    food_id: int
    paid: bool = False


class ClaimIn(BaseModel):
    user_id: int


def run(fn, *args):
    try:
        return fn(*args)
    except logic.RuleError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/", response_class=HTMLResponse)
def home():
    return INDEX.read_text(encoding="utf-8")


@app.get("/api/state")
def get_state():
    return logic.state()


@app.post("/api/orders")
def place_order(body: OrderIn):
    return {"order_id": run(logic.place_order, body.user_id, body.food_id, body.paid)}


@app.post("/api/orders/{order_id}/skip")
def skip_time(order_id: int):
    run(logic.skip_time, order_id)
    return {"ok": True}


@app.post("/api/orders/{order_id}/cancel")
def cancel(order_id: int):
    return run(logic.cancel_order, order_id)


@app.post("/api/offers/{offer_id}/claim")
def claim(offer_id: int, body: ClaimIn):
    return {"order_id": run(logic.claim_offer, offer_id, body.user_id)}


@app.post("/api/reset")
def reset():
    logic.reset()
    return {"ok": True}


@app.get("/metrics", response_class=PlainTextResponse)
def metrics():
    """Prometheus-style counters (matches the 'What we track' slide)."""
    s = logic.state()["stats"]
    return "\n".join(f"cloudbite_{k} {v}" for k, v in s.items()) + "\n"


@app.get("/health")
def health():
    return {"status": "ok"}

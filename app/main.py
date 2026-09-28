"""FastAPI server for CollectMind. Run: uvicorn app.main:app --reload"""
from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from . import agent  # noqa: E402

STATIC = Path(__file__).resolve().parent.parent / "static"
app = FastAPI(title="CollectMind - memory-powered collections copilot")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


class VisitIn(BaseModel):
    borrower_id: str
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    officer: str
    met: str
    approach: str
    outcome: str
    collected: int = 0
    promise_date: str = ""
    notes: str = Field(min_length=5)
    recommended_approach: str = ""
    followed_recommendation: bool = False


class AskIn(BaseModel):
    question: str = Field(min_length=3)
    borrower_id: str | None = None


def _wrap(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except KeyError:
        raise HTTPException(404, "Borrower not found")
    except Exception as e:  # surface memory/LLM outages clearly in the UI
        raise HTTPException(502, f"{type(e).__name__}: {e}")


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/mode")
def get_mode():
    return agent.mode()


@app.get("/api/borrowers")
def borrowers():
    out = []
    for b in agent.load_borrowers():
        b["visit_count"] = len(agent.load_visits(b["id"]))
        out.append(b)
    return out


@app.get("/api/borrowers/{bid}/visits")
def visits(bid: str):
    return agent.load_visits(bid)


@app.get("/api/borrowers/{bid}/brief")
def brief(bid: str, memory: bool = True):
    return _wrap(agent.build_brief, bid, use_memory=memory)


@app.post("/api/visits")
def add_visit(v: VisitIn):
    return _wrap(agent.log_visit, v.model_dump())


@app.post("/api/ask")
def ask(q: AskIn):
    return {"answer": _wrap(agent.ask, q.question, q.borrower_id)}

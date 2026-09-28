"""CollectMind agent: turns loan data + Hindsight memory into visit briefs, and learns from every visit."""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from .llm import LLMError, chat_json
from .memory import borrower_tag, get_memory

DATA = Path(__file__).resolve().parent.parent / "data"
VISITS_LOG = DATA / "visits_log.json"  # new visits logged through the app (the "CBS" record)

memory = get_memory()

BRIEF_SYSTEM = """You are CollectMind, a collections copilot for field officers of an Indian microfinance institution.
Write a pre-visit brief. Be concrete and practical, like an experienced senior officer.
Follow the RBI Fair Practices Code: no threats, no public shaming, visits only 8 AM-7 PM, respect privacy.
Only use facts given to you. If there are no past memories, say so honestly and give sensible first-visit guidance.
Return JSON with exactly these keys:
{
 "headline": "one sentence summary of the situation",
 "risk_level": "Low | Medium | High",
 "risk_reason": "short reason",
 "willful_or_distress": "Likely wilful | Likely genuine distress | Unknown",
 "best_time_and_place": "when and where to meet",
 "who_to_meet": "person(s) to talk to",
 "recommended_approach": "the single best approach, 1-2 sentences",
 "talking_points": ["3-4 short points to say"],
 "avoid": ["2-3 things NOT to do"],
 "promise_reliability": "how reliable this borrower's promises are, or Unknown",
 "memory_evidence": ["which remembered facts drove this advice, each with its date; empty list if none"]
}"""


def load_borrowers() -> list[dict]:
    return json.loads((DATA / "borrowers.json").read_text())


def get_borrower(bid: str) -> dict:
    for b in load_borrowers():
        if b["id"] == bid:
            return b
    raise KeyError(bid)


def load_visits(bid: str | None = None) -> list[dict]:
    visits = json.loads((DATA / "visit_history.json").read_text())
    if VISITS_LOG.exists():
        visits += json.loads(VISITS_LOG.read_text())
    if bid:
        visits = [v for v in visits if v["borrower_id"] == bid]
    return sorted(visits, key=lambda v: v["date"])


def visit_to_text(v: dict, b: dict) -> str:
    """Turn a structured visit record into a natural-language note for Hindsight to learn from."""
    parts = [
        f"On {v['date']}, loan officer {v['officer']} visited borrower {b['name']} ({b['id']}), "
        f"a {b['occupation']} from {b['village']} with a {b['loan_type']} (EMI Rs {b['emi']}).",
        f"Met: {v['met']}. Collection approach used: {v['approach']}. Outcome: {v['outcome']}.",
    ]
    if v.get("collected"):
        parts.append(f"Amount collected: Rs {v['collected']}.")
    if v.get("promise_date"):
        parts.append(f"Borrower promised to pay by {v['promise_date']}.")
    if v.get("recommended_approach"):
        followed = "followed" if v.get("followed_recommendation") else "did NOT follow"
        parts.append(f"CollectMind had recommended: '{v['recommended_approach']}'. The officer {followed} "
                     f"this recommendation, and the outcome was {v['outcome']}.")
    parts.append(f"Officer notes: {v['notes']}")
    return " ".join(parts)


def visit_tags(b: dict) -> list[str]:
    return [borrower_tag(b["id"]), f"segment:{b['segment']}", f"officer:{b['officer']}"]


def retain_visit(v: dict) -> None:
    b = get_borrower(v["borrower_id"])
    memory.retain_visit(
        content=visit_to_text(v, b),
        tags=visit_tags(b),
        when=datetime.fromisoformat(v["date"]),
        doc_id=f"visit-{v['id']}",
    )


def _loan_facts(b: dict) -> str:
    return (f"Borrower: {b['name']} ({b['id']}), {b['occupation']}, {b['village']}\n"
            f"Loan: {b['loan_type']}, group: {b['group']}, sanctioned Rs {b['sanctioned']}, "
            f"outstanding Rs {b['outstanding']}, EMI Rs {b['emi']} due on day {b['emi_day']} each month\n"
            f"Overdue EMIs: {b['overdue_emis']}, days past due: {b['dpd']}\n"
            f"Today's date: {datetime.now().date().isoformat()}")


def _fallback_brief(b: dict) -> dict:
    """Used when the LLM is unavailable: still useful, built straight from memory."""
    return {
        "headline": f"{b['name']} is {b['dpd']} days past due with {b['overdue_emis']} EMI(s) overdue.",
        "risk_level": "High" if b["dpd"] > 60 else "Medium" if b["dpd"] > 30 else "Low",
        "risk_reason": "Based on days past due only (AI summary unavailable).",
        "willful_or_distress": "Unknown",
        "best_time_and_place": "Home visit between 8 AM and 7 PM.",
        "who_to_meet": b["name"],
        "recommended_approach": "Polite reminder; ask about the reason for delay and agree a specific date.",
        "talking_points": ["Confirm the overdue amount", "Ask about income situation", "Agree a written promise date"],
        "avoid": ["Threats or raised voice", "Discussing the loan in front of neighbours"],
        "promise_reliability": "Unknown",
        "memory_evidence": [],
    }


def build_brief(bid: str, use_memory: bool = True) -> dict:
    b = get_borrower(bid)
    borrower_mems, peer_mems = [], []
    if use_memory:
        # 1) What do we remember about THIS borrower?
        borrower_mems = memory.recall(
            f"{b['name']} repayment behaviour, income cycle, promises kept or broken, family members, "
            f"which collection approach worked or failed",
            tags=[borrower_tag(bid)],
        )
        # 2) What have we learned from SIMILAR borrowers (same segment)?
        peer_mems = [m for m in memory.recall(
            f"which collection approaches worked or failed for {b['segment']} borrowers",
            tags=[f"segment:{b['segment']}"], max_tokens=1024,
        ) if b["name"].split()[0] not in m.text][:5]

    mem_block = "\n".join(f"- [{m.date or 'undated'}] {m.text}" for m in borrower_mems) or "NONE - first visit, no history."
    peer_block = "\n".join(f"- [{m.date or 'undated'}] {m.text}" for m in peer_mems) or "NONE"
    prompt = (f"{_loan_facts(b)}\n\nMEMORIES ABOUT THIS BORROWER (from past visits):\n{mem_block}\n\n"
              f"LESSONS FROM SIMILAR BORROWERS ({b['segment']}):\n{peer_block}")
    if not use_memory:
        prompt = _loan_facts(b) + "\n\n(Memory is switched OFF: you only know the loan record above.)"

    try:
        brief = chat_json(BRIEF_SYSTEM, prompt)
        source = "llm"
    except LLMError:
        brief = _fallback_brief(b)
        source = "fallback"

    return {
        "borrower": b,
        "brief": brief,
        "memory_on": use_memory,
        "source": source,
        "recalled": [m.__dict__ for m in borrower_mems],
        "peer_lessons": [m.__dict__ for m in peer_mems],
    }


def log_visit(v: dict) -> dict:
    """Save a new visit to the log AND retain it into Hindsight so the agent learns from it."""
    get_borrower(v["borrower_id"])  # validates id
    existing = json.loads(VISITS_LOG.read_text()) if VISITS_LOG.exists() else []
    v["id"] = f"N{len(existing) + 1:03d}-{v['borrower_id']}"
    v["collected"] = int(v.get("collected") or 0)
    existing.append(v)
    VISITS_LOG.write_text(json.dumps(existing, indent=1))
    retain_visit(v)
    return v


def ask(question: str, bid: str | None = None) -> str:
    """Free-form question answered by Hindsight reflect (scoped to one borrower or whole portfolio)."""
    tags = [borrower_tag(bid)] if bid else None
    return memory.reflect(question, tags=tags)


def mode() -> dict:
    return {"memory": memory.mode, "llm": "groq" if os.getenv("GROQ_API_KEY") else "none"}

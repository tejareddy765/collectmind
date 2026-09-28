"""Memory layer for CollectMind.

All long-term memory lives in a Hindsight memory bank. Every field visit is
*retained* as a memory tagged with the borrower, their segment and village, so
we can later *recall* memories for one borrower, or *reflect* across the whole
portfolio to learn which collection approaches work.

`OfflineMemory` is a tiny stand-in used only when OFFLINE_MODE=1, so the UI can
be developed without API keys. It is NOT used in the real demo.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

BANK_MISSION = (
    "I am CollectMind, a collections copilot for field officers of an Indian microfinance "
    "institution. I remember every borrower visit: repayment behaviour, reasons for delay, "
    "promises made and whether they were kept, who in the family controls money, and which "
    "collection approach worked or failed. I use this to recommend respectful, effective, "
    "RBI Fair Practices Code compliant recovery approaches."
)

RETAIN_INSTRUCTIONS = (
    "Extract facts about: repayment behaviour and timing patterns (e.g. pays after harvest), "
    "income sources and cash-flow cycles, reasons given for delay, promises made and whether "
    "they were kept, family members involved in money decisions, the collection approach used "
    "and its outcome, and borrower preferences about how to be contacted."
)

DIRECTIVES_NOTE = (
    "Never recommend harassment, threats, public shaming, or visits outside 8 AM - 7 PM "
    "(RBI Fair Practices Code)."
)


@dataclass
class Memory:
    text: str
    type: str = "world"
    date: str | None = None


def borrower_tag(borrower_id: str) -> str:
    return f"borrower:{borrower_id}"


class HindsightMemory:
    """Thin wrapper around the official hindsight-client SDK."""

    mode = "hindsight"

    def __init__(self, base_url: str, api_key: str | None, bank_id: str):
        from hindsight_client import Hindsight

        self.client = Hindsight(base_url=base_url, api_key=api_key or None, timeout=120)
        self.bank_id = bank_id

    def ensure_bank(self) -> None:
        """Create (or update) the bank with our mission and extraction instructions."""
        self.client.create_bank(
            bank_id=self.bank_id,
            name="CollectMind - Collections Memory",
            mission=BANK_MISSION + " " + DIRECTIVES_NOTE,
            retain_custom_instructions=RETAIN_INSTRUCTIONS,
            disposition={"skepticism": 4, "literalism": 2, "empathy": 4},
        )

    def retain_visit(self, content: str, tags: list[str], when: datetime, doc_id: str) -> None:
        self.client.retain(
            bank_id=self.bank_id,
            content=content,
            context="field collection visit note written by a loan officer",
            timestamp=when,
            document_id=doc_id,
            tags=tags,
        )

    def recall(self, query: str, tags: list[str] | None = None, max_tokens: int = 2048) -> list[Memory]:
        resp = self.client.recall(
            bank_id=self.bank_id,
            query=query,
            tags=tags,
            tags_match="any_strict" if tags else "any",
            max_tokens=max_tokens,
            budget="mid",
        )
        out = []
        for r in resp.results or []:
            date = getattr(r, "occurred_start", None) or getattr(r, "mentioned_at", None)
            out.append(Memory(text=r.text, type=getattr(r, "type", "world") or "world",
                              date=str(date)[:10] if date else None))
        return out

    def reflect(self, query: str, tags: list[str] | None = None) -> str:
        resp = self.client.reflect(
            bank_id=self.bank_id,
            query=query,
            tags=tags,
            tags_match="any_strict" if tags else "any",
            budget="mid",
        )
        return resp.text


class OfflineMemory:
    """Dev-only fallback: stores notes in a JSON file, keyword-based recall."""

    mode = "offline"

    def __init__(self, path: Path):
        self.path = path
        self.items: list[dict] = json.loads(path.read_text()) if path.exists() else []

    def _save(self):
        self.path.write_text(json.dumps(self.items, indent=1))

    def ensure_bank(self) -> None:
        pass

    def retain_visit(self, content, tags, when, doc_id):
        self.items = [i for i in self.items if i["doc_id"] != doc_id]
        self.items.append({"text": content, "tags": tags, "date": when.date().isoformat(), "doc_id": doc_id})
        self._save()

    def recall(self, query, tags=None, max_tokens=2048):
        words = set(re.findall(r"[a-z]+", query.lower()))
        pool = [i for i in self.items if not tags or set(tags) & set(i["tags"])]
        scored = sorted(pool, key=lambda i: (-len(words & set(re.findall(r"[a-z]+", i["text"].lower()))), i["date"]))
        return [Memory(text=i["text"], type="experience", date=i["date"]) for i in scored[:12]]

    def reflect(self, query, tags=None):
        mems = self.recall(query, tags)
        if not mems:
            return "No memories yet."
        return "(offline mode) Relevant memories:\n" + "\n".join(f"- [{m.date}] {m.text}" for m in mems[:8])


def get_memory():
    if os.getenv("OFFLINE_MODE") == "1":
        return OfflineMemory(Path(__file__).resolve().parent.parent / "data" / "offline_memory.json")
    return HindsightMemory(
        base_url=os.getenv("HINDSIGHT_BASE_URL", "https://api.hindsight.vectorize.io"),
        api_key=os.getenv("HINDSIGHT_API_KEY"),
        bank_id=os.getenv("HINDSIGHT_BANK_ID", "collectmind-collections"),
    )

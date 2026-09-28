"""Load past visit history into Hindsight so the agent starts with months of field experience.

Usage:  python -m scripts.seed_memory
Each visit is retained with its real date (timestamp), so Hindsight can reason about time
("broke the promise made in July", "pays after harvest").
"""
from dotenv import load_dotenv

load_dotenv()

from app import agent  # noqa: E402


def main():
    agent.memory.ensure_bank()
    visits = [v for v in agent.load_visits()]
    for i, v in enumerate(visits, 1):
        agent.retain_visit(v)
        print(f"[{i}/{len(visits)}] retained {v['id']} {v['date']} {v['borrower_id']} - {v['outcome']}")
    print(f"Done. Memory mode: {agent.memory.mode}")


if __name__ == "__main__":
    main()

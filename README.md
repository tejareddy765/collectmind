# CollectMind: a collections copilot that remembers every borrower

**CollectMind** helps field loan officers at Indian microfinance institutions, cooperative banks and SHG/JLG lenders prepare for collection visits. It uses [Hindsight](https://hindsight.vectorize.io/) memory, so it learns from every visit: who pays after harvest, whose promises break, whose wife controls the cash, and which approach actually works.

## The problem

A field officer visits 15 to 25 overdue borrowers a day. What worked last time lives in a paper diary or in the head of an officer who got transferred. So every visit starts from zero. The officer uses the wrong approach, goes on the wrong day, embarrasses the borrower in public, and recovery drops. Genuine distress cases also get treated like wilful defaulters.

## What CollectMind does

| Step | What happens | Hindsight operation |
|---|---|---|
| **Brief me** | Before a visit, CollectMind gives the officer a brief: risk, wilful vs distress, best time and place, who to meet, the recommended approach, what to say and what to avoid. | `recall` (tagged to the borrower, plus lessons from similar borrowers) |
| **Log visit** | After the visit, the officer records the approach used, the outcome and notes. It also records whether they followed CollectMind's advice. | `retain` (with the real visit date and tags) |
| **Learn** | CollectMind's next brief uses what happened. If its advice failed, it knows. | Observations are consolidated automatically by Hindsight |
| **Ask CollectMind** | Portfolio questions such as "Which approaches work for agri borrowers?" or "Who needs restructuring?" | `reflect` |

## The learning curve (the demo)

1. **Anjali Bai** is a new borrower with no memory, so her brief is generic and honestly says it has no history.
2. Log one visit ("husband sells at rythu bazaar, cash comes on Sundays").
3. Brief again. The advice now says to visit on Sunday after the bazaar.
4. **Ramesh Goud** has 5 remembered visits. Click **Compare: without vs with memory**:
   - Without memory: "Polite reminder, agree a date."
   - With memory: "Don't push before the November harvest. Go with JLG leader Narsimha in the evening and involve his wife Lakshmi, who controls the cash. His pre-harvest promises are unreliable (he broke the 20 July promise)."

## How Hindsight memory is used

- **One memory bank** (`collectmind-collections`) with a *mission* (collections copilot), *custom retain instructions* (extract repayment patterns, income cycles, promises and whether they were kept, family decision-makers, approach → outcome), and a *disposition* (skeptical about promises, empathetic about distress).
- **Retain:** each visit becomes a natural-language note, stored with:
  - `timestamp` set to the real visit date, so Hindsight can reason over time ("broke the promise made in July", "pays after harvest")
  - `tags`: `borrower:<id>`, `segment:<agri|dairy|...>`, `officer:<name>`
  - `document_id` set to the visit id, which makes it idempotent (re-seeding doesn't duplicate)
- **Recall:** two scoped recalls per brief:
  1. `tags=[borrower:<id>]` with `tags_match="any_strict"`, which returns only this borrower's memories
  2. `tags=[segment:<x>]`, which returns lessons learned from similar borrowers (knowledge transfer across the portfolio)
- **Feedback loop:** when an officer logs a visit, CollectMind also retains *what it had recommended*, *whether the officer followed it* and *the outcome*. Its own advice becomes experience it learns from.
- **Reflect:** the *Ask CollectMind* tab uses `reflect` across the whole bank or a single borrower for questions no single note answers.
- **Memory OFF toggle:** the same LLM prompt runs with no recalled memories, which proves the improvement comes from memory.

## Architecture

```
static/index.html   single-page UI (vanilla JS)
app/main.py         FastAPI routes
app/agent.py        brief building, visit logging, ask  ← the agent logic
app/memory.py       Hindsight wrapper (retain / recall / reflect) + offline dev stub
app/llm.py          Groq client: JSON mode, retries, 429 backoff, model fallback
data/               synthetic borrowers + 20 historical visits (Mar–Sep 2026)
scripts/seed_memory.py   loads history into Hindsight
```

**Handling failures:**
- The LLM tries `openai/gpt-oss-120b` first, then falls back to `qwen/qwen3-32b`.
- It strips `<think>` blocks and code fences before parsing JSON.
- If every model fails, CollectMind still shows a basic brief along with the recalled memories.
- Memory and API errors show up as clear messages in the UI.

**Compliance:** the prompt and the bank mission follow the RBI Fair Practices Code: no threats, no public shaming, visits only between 8 AM and 7 PM.

## Run it

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # add HINDSIGHT_API_KEY and GROQ_API_KEY
python -m scripts.seed_memory      # loads 20 past visits into Hindsight (takes a minute)
uvicorn app.main:app --reload
# open http://localhost:8000
```

- Get a Hindsight Cloud key at https://ui.hindsight.vectorize.io (add promo code `MEMHACK99` under Billing).
- Get a Groq key at https://console.groq.com/keys.
- To try the UI without keys, set `OFFLINE_MODE=1`. This uses a local JSON file instead of Hindsight and is for development only.

## Real-world path

This plugs into a core banking system's overdue list (e.g. an Oracle APEX CBS through REST). A mobile version would let officers record visit notes by voice in Telugu or Hindi. Pricing could be per officer per month for MFIs and cooperative banks.

*All borrower data is synthetic.*

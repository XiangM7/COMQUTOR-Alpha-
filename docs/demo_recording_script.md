# W6 Demo Recording Script

Target length: 3–5 minutes. The automated recording has no narration; this script is for the
human investor-facing voice-over.

## 0:00–0:30 — Product

1. Open `http://127.0.0.1:5175/research`.
2. Say: “COMQUTOR turns multi-agent research into traceable Alpha structures and explicit
   conflicts. This is a local research Demo, not an autonomous trading system.”
3. Point to `API ready` and `Real execution disabled`.

## 0:30–1:35 — NVDA Research and Graph

1. Enter `NVDA`, date `2026-06-30`; leave all four analysts selected; click **Start research**.
2. Say: “The completed approved fixture is reused without a Provider call.”
3. Scroll to **Analyst findings**. Say: “Agent text is converted into bounded structured claims
   with source identity, evidence, factors, direction and confidence.”
4. Click **Structure Graph**.
5. Say: “The graph merges claims by Alpha structure instead of voting by agent.”
6. Point to `A101` and select `A304 Valuation Risk`.
7. Say: “Deterministic activation exposes AI-driven GPU demand and valuation risk as separate,
   inspectable structures.”

## 1:35–2:25 — NVDA Conflict and Evidence

1. Click **Conflict Radar**.
2. Point to **A101 vs A304**.
3. Say: “The backend admits this taxonomy-defined pair and arbitrates it deterministically.”
4. Scroll to **Evidence traceability**.
5. Say: “Each side links back to structured claims and preserved evidence. The browser never
   receives raw Provider output, credentials or hidden reasoning.”

## 2:25–3:35 — QQQ

1. Return to **Research**; enter `QQQ`, date `2026-06-30`; click **Start research**.
2. Click **Structure Graph** and point to `A003`.
3. Click **Conflict Radar**.
4. Point to **A001 vs A501** and **A003 vs A501** under **All admitted conflicts**.
5. Say: “QQQ has two admitted conflicts. The main conflict is the first result returned by the
   backend arbitration; the frontend does not hardcode a winner.”

## 3:35–4:10 — Boundary and Close

1. Say: “NVDA and QQQ are the two approved Golden cases. MSFT remains blocked by a taxonomy
   specification conflict, and the five-ticker Gate is not claimed.”
2. Say: “The local Demo supports SQLite and has PostgreSQL integration verification. Live
   Provider execution, authentication, tenant ownership and public production deployment are
   outside this release candidate.”
3. End: “COMQUTOR’s value is not another summary. It is a deterministic, auditable readout of
   which Alpha structures are active, where they conflict, and what evidence supports them.”

Automated browser recording:

    ./scripts/record_w6_demo.sh

Output: `.demo/w6/recordings/comqutor_alpha_w6_demo.webm` with a printed SHA-256. The file is
local and ignored by Git.

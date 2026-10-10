# Architecture

You write a **builder**. It reads a bank brief and creates a **phone agent** on Freya's platform. Freya tests that agent against simulated customers and a mock bank, and the score comes from the bank's records plus a judge's reading of the transcript.

## 1. Architecture

Three parties are involved:
- **Your side (this repo):** the builder, the API client and the test runner. This is the only part you write.
- **Freya platform:** hosts the phone agent and runs the simulation, the AI customer and the judge. The agent's model is fixed by Freya.
- **Mock bank:** exposes the seven tools the agent calls and keeps a ledger of what actually happened. The scorer trusts the ledger, not the agent's words.

```mermaid
flowchart LR
    subgraph You["Your side (this repo)"]
        Brief["Brief (.md)"]
        API["tools/openapi.json"]
        Builder["Builder<br/>agent_builder.py + SKILL.md"]
        Client["freya.py"]
        Runner["run_cases.py + score.py"]
        Cases["public-test-set.json"]
    end

    subgraph Freya["Freya platform"]
        WF["Phone agent (workflow)"]
        Sim["Simulation engine"]
        Cust["AI customer"]
        Judge["Judge"]
    end

    subgraph Bank["Mock bank"]
        Tools["7 tool endpoints"]
        Ledger[("Ledger")]
    end

    Brief --> Builder
    API --> Builder
    Builder --> Client
    Client -->|save_workflow| WF
    Cases --> Runner
    Runner --> Client
    Client -->|run simulation| Sim
    Sim --> Cust
    Sim --> WF
    WF -->|tool calls| Tools
    Tools --> Ledger
    Sim --> Judge
    Runner -->|read ledger| Ledger
    Runner -->|read verdict| Judge
```

## 2. Sequence: building the agent

Claude reads the brief and writes a workflow JSON. It saves it to Freya (updating the same workflow each time, never creating a new one), tests it on the practice customers and fixes what fails, at most three times. The builder's trace is written to `traces/` and is part of what you submit.

```mermaid
sequenceDiagram
    actor You
    participant B as agent_builder.py
    participant C as Claude (skill)
    participant F as freya.py
    participant P as Freya platform
    participant R as run_cases.py

    You->>B: run with brief file(s)
    B->>C: build a phone agent for these briefs
    C->>C: read brief, openapi.json, docs
    C->>C: write out/<brief>.workflow.json
    C->>F: save_workflow
    F->>P: create or update, then publish
    P-->>F: workflow_id, agent_id
    loop up to 3 times
        C->>R: run practice customers
        R-->>C: PASS/FAIL with reasons
        C->>C: edit workflow file
        C->>F: save_workflow (same slot)
    end
    C-->>B: workflow_id, agent_id, score
    B-->>You: done, trace in traces/
```

## 3. Sequence: grading one customer

An AI customer talks to the phone agent, and every tool call lands in the bank's ledger. Afterwards two checks run: the ledger is compared with the expected records, and a judge reads the transcript for policy and honesty. A case passes only if both pass, with no partial credit. In the final, each case runs three times and all three must pass.

```mermaid
sequenceDiagram
    participant R as run_cases.py
    participant Bk as Mock bank
    participant P as Freya simulation
    participant Cu as AI customer
    participant A as Phone agent
    participant J as Judge
    participant S as score.py

    R->>Bk: open session for the case
    Bk-->>R: customer_id, call variables
    R->>P: create persona, start simulation

    loop the call
        P->>A: customer speaks
        A->>Bk: tool call
        Bk-->>A: result (and ledger entry)
        A-->>P: reply
        P->>Cu: reply
        Cu-->>P: next line
    end

    P->>J: transcript and checks
    J-->>P: pass/fail
    R->>Bk: read ledger
    Bk-->>R: outcome, promises, notes, callbacks, transfers
    R->>S: compare with expected
    S-->>R: ledger pass/fail
    R->>R: PASS only if ledger and judge both pass
```

# Hackathon materials — Freya "Build the Builder"

| File | What it is |
|---|---|
| [kickoff-email.md](kickoff-email.md) | Kickoff email from the Freya team (links, key setup, timeline) |
| [hackathon-page.md](hackathon-page.md) | Full https://www.freyavoice.ai/hackathon page: overview, data, evaluation, submission, rules, FAQ, practice-case table |
| [paper.pdf](paper.pdf) / [paper.md](paper.md) | ττ-bench paper (arXiv 2609.04611) with a takeaways summary at the top |
| [kickoff-transcript.md](kickoff-transcript.md) | Kickoff recording link (transcript not available) |

Full practice-case details: [`public-test-set.json`](../../public-test-set.json) at the repo root.

## Timeline (Pacific Time)
| Event | UTC | PT |
|---|---|---|
| Start (kit and keys) | Sat Oct 10, 10:00 | Sat Oct 10, 3:00 AM |
| Hidden briefs open | Sun Oct 11, 17:00 | **Sun Oct 11, 10:00 AM** |
| Submissions close | Sun Oct 11, 20:00 | **Sun Oct 11, 1:00 PM** |
| Results | after review | |

The 3-hour window is for running the builder and fixing bugs, not tuning to the hidden briefs.

## Key rules
- Solo or team of two; one Freya key/workspace per team; one practice simulation at a time.
- Submit a **builder**: one command, brief in → phone agent out, no manual edits. Run: `python3 builder/build.py {brief_path} {tool_api_path}`.
- Builder run time ≤ 30 min per brief (incl. self-tests). Any model for the builder; the phone agent must use the Freya model set in `freya.py`.
- After hidden briefs open: bug fixes allowed, but nothing from a hidden brief (rules, values, names) may go into the builder.
- Phone agent may only call the kit's tool API. Update workflows in place (200 per workspace max).
- Submit: exported workflows (`freya.export_workflow`) + one trace per hidden brief committed to the repo, plus the JSON form, before close. Remove API keys from traces.
- Top 10 builders are rerun and traces reviewed; entries scoring clearly below on rerun are removed.

## Scoring
- Score = cases passed / 60 (2 hidden briefs × 30 customers; one brief is clean, one is raw bank material).
- Each case runs 3×; passes only if all 3 pass. A run passes only if **Outcome** (ledger correct), **Policy** (stayed in brief) and **Honesty** (no false claims) all pass. Correct refusals (e.g. disputes) count.
- Tie-breaks: total promised amount on passed cases → shorter build time (from traces) → earlier submission.
- Prizes: 1st YC interview, 2nd AirPods, top 3 final interview with Freya, $3,000 Freya credits pool.

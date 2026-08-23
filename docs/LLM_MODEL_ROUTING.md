# LLM Model Routing

BRD 6: *"LLM usage shall be cost-aware, given eventual scaling to nationwide
bill volume (150,000+ bills/year)."* The Roadmap names the mechanism:
caching, plus a cheap model ahead of the higher-cost one.

Caching is built and running (see `summary_input_hash` — unchanged bills are
skipped without a model call). This documents the second half: **what got
measured, what the numbers actually say, and why routing ships disabled.**

## Measurements

Run 2026-08-23 against real 2026-session Florida bills with full bill text,
same prompts, only the model differing. `llama3.1:8b` is the current
production model; `llama3.2` (3.2B) is the cheap candidate. Both Q4_K_M on
the same RTX 5070.

| | llama3.1:8b | llama3.2 (3B) |
|---|---|---|
| Non-answers on "who it affects" (12 bills) | **3/12** | **6/12** |
| Avg "who it affects" length | 305 chars | 170 chars |
| Avg "what it does" length | 407 chars | 435 chars |
| Time per bill (both prompts) | 3.1s | 1.4s |
| Extrapolated to 150,000 bills/yr | ~128 GPU-hours | ~58 GPU-hours |

"Non-answer" means the model returned the prompt's own fallback string,
*"The available text does not specify a particular affected group beyond the
general public."* It's a useful objective quality metric because the prompt
defines it explicitly, so it needs no human judgement to count.

## What the numbers say

**The quality gap is not uniform across the two prompts.** That is the whole
finding:

- **"who it affects" degrades badly on the small model** — twice the
  non-answer rate, and roughly half the length when it does answer. This is
  precisely the field that justified moving from the short blurb to full
  bill text, so regressing it would undo that work.
- **"what it does" is comparable.** Side-by-side on real bills, both models
  produced accurate summaries. The 8B tends to include an extra concrete
  detail (an effective date, say), so it is not strictly equal — but there
  was no accuracy difference.

So routing is **per field, not per bill**. `FAST_MODEL_CLAIM_TYPES` lists
the fields a cheap model may write; `who_it_affects` is deliberately not in
it.

## Why it ships disabled

`OLLAMA_MODEL_FAST` defaults to empty, meaning every field uses the quality
model. Turning it on is a config change, not a code change.

At Florida-only scale the saving does not justify any quality loss:

- The full corpus is ~2,300 bills, and caching means a steady-state run
  re-summarizes only what changed — usually a handful of bills.
- Even the worst case, re-summarizing everything, is about two hours of
  local GPU time on hardware that is already paid for. There is no
  per-token cost to avoid.
- Routing "what it does" to the 3B saves roughly 27% of generation time —
  real, but 27% of a number that is already negligible.

**When to enable it:**

1. **Nationwide expansion.** At 150,000 bills/year the numbers above stop
   being rounding errors.
2. **Moving to a hosted LLM API.** `docs/AWS_MIGRATION.md` notes that a
   cloud migration probably means swapping Ollama for a hosted API, where
   cost is per-token and this routing turns into actual money.

Until one of those is true, spending quality to save GPU-hours on idle
home-lab hardware is the wrong trade.

## Enabling it

```bash
# in .env
OLLAMA_MODEL_FAST=llama3.2:latest
```

Then redeploy the backend and run the batch job. No manual invalidation is
needed: the fast model is part of the input fingerprint, so every affected
bill is detected as stale and regenerated automatically.

Two things to know before you do:

- **It triggers a full re-summarization** of every bill whose "what it does"
  the cheap model would now write. That is correct — the output genuinely
  changes — but it is not free, and it rewrites public-facing text.
- **Claims record which model wrote them** (`generated_by`), so after
  enabling, the two fields on a bill can legitimately show different models.
  That is intended, and matters when reviewing a flagged claim.

## Re-checking the measurements

The numbers above are specific to these two models and these prompts. Re-run
the comparison if either changes — particularly `PROMPT_VERSION`, since a
reworded "who it affects" prompt could plausibly close the gap and make a
cheaper model viable for that field too.

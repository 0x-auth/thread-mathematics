# Thread Coordinate Router — Product Requirements Document

**Working name:** XAX / thread-router
**Author:** Space (Abhishek Srivastava)
**Status:** Draft v1 — definition phase
**Date:** August 2026

---

## 0. One-line statement

**Every answer already exists at a permanent, computable coordinate. Build the router, not another knowledge base.**

---

## 1. Problem Statement

### 1.1 The observed problem

In any organization running technical support through chat, the same questions are answered repeatedly by the same engineers. At Expedia this was concretely visible across:

- `#ask-eg-vault` — HashiCorp Vault support
- `#venafi-support` — certificate management
- `#ask-rcp-support` — Kubernetes/RCP platform

The answer to a newly-asked question almost always already exists. It exists in:

1. A Slack thread from three months ago, in this channel
2. A Slack thread in a *different* channel (cross-domain: a Vault question whose real answer is a Venafi answer)
3. A Confluence page nobody reads
4. A GitHub issue closed two years ago
5. A commit message

The knowledge is not missing. **The knowledge is distributed and unaddressed.**

### 1.2 Why existing approaches fail

| Approach | Why it fails |
|---|---|
| Write more Confluence docs | Adds a 6th silo. Nobody reads it. Staleness is unbounded. |
| Slack search | Ranks by recency/relevance, not correctness. Returns the *question*, not the verified answer. Users don't search before asking. |
| LLM chatbot trained on corpus | Expensive, hallucinates, loses provenance, requires retraining, and answers *confidently* when wrong. Destroys the audit trail. |
| RAG over the corpus | Better, but still *generates* an answer rather than pointing at the human-verified one. Provenance is a citation, not the artifact. |
| A CLI search tool (phi-thread) | See §2.2 — the failure is architectural, analyzed below. |

### 1.3 The reframe

Do not generate answers. **Route to the coordinate where the verified answer already lives.**

This preserves:
- **Provenance** — the answer is a link to a real human's real message, with their name on it
- **Correctness** — a human already verified it in context
- **Freshness** — if the answer is wrong, someone replies to *that thread*, and the correction is in the same place
- **Zero hallucination surface** — the system emits URLs, never prose

---

## 2. Prior Art (what we already learned)

### 2.1 The Expedia precedent — what worked

A pattern-language KB deployed across three support channels. Architecture:

1. **Pre-curated pattern database.** Human experts wrote problem→solution patterns (`PathStructure`, `AuthnPattern`, `CertRequestPattern`, `KubefedPattern`…) with Context / Problem / Solution / Related Patterns.
2. **Each pattern posted as a thread reply**, and its `ts` recorded to a flat file:
   ```
   # vault-timestamps.txt
   PathStructure=1747590953.711699
   AuthnPattern=1747590954.711719
   ServiceAccountag=1747590955.711739
   ```
   *This file is the entire index.* Pattern ID → thread coordinate.
3. **Keyword-triggered bot.** Non-AI. On seeing `403 forbidden`, `preflight capability`, `permission denied` etc. in-channel, it matched a pattern and posted the permalink.
4. **Cross-channel edges.** `VenafiVaultPattern` (in `#ask-eg-vault`) linked to `CertRequestPattern` (in `#venafi-support`) with a weight of 0.9.
5. **Feedback loop.** 👍/👎 reactions adjusted pattern confidence.

**Why this worked:** it fired *where the question was asked*, at *write time*, with *zero latency*, against a *human-curated* index.

### 2.2 The phi-thread attempt — what failed, and why

phi-thread (v0.2.0, PyPI) generalized the coordinate idea across Stack Overflow, Reddit, HN, GitHub, and DuckDuckGo. It did not succeed. The diagnosis:

**It violated its own stated principle.** From the XAX notes: *"I am where I am REFERENCED, not where I am stored."* phi-thread is a CLI you must go to. That is storage, not reference.

Three concrete failure modes:

1. **Read-time, not write-time.** The user must (a) know phi-thread exists, (b) remember it mid-problem, (c) leave their workflow and open a terminal. Every knowledge tool requiring a context switch dies. The Expedia bot required *nothing* of the user — they just asked their question as normal.

2. **It competed with Google on Google's terms and lost.** Ranking was `platform_score × keyword_intersection`. That is 1998-era IR against a trillion-dollar ranking system. And the "deep link to the accepted answer" is not a moat — Stack Overflow already renders the accepted answer at the top of the page.

3. **No curation, no cold-start answer.** The index "built itself" from whatever live search returned. Nobody verified correctness. The first N users got nothing. Latency was 5–15s.

**Lesson, stated as a requirement:** *The router must sit at the point of asking, not at the point of storing. The index must be curated by domain humans, not scraped.*

### 2.3 The webhook question

An earlier XAX iteration ran with no webhook — a human ran extraction scripts and pasted results into `#x-_a-_x` manually ("the webhook is YOU"). This is a legitimate **Phase 0**: it validates whether the routed answers are useful before building automation. It is not a permanent architecture — it does not survive the author going on holiday. Treat manual operation as a deliberate validation stage with an explicit exit criterion (§9).

---

## 3. The Core Primitive — Thread Coordinates

### 3.1 The claim (empirically verified)

Every message in a threaded system has a permanent, deterministic address of the form:

```
(namespace, container, thread_anchor, message_time)
```

For Slack:
```
https://{workspace}.slack.com/archives/{CHANNEL}/p{OWN_TS}?thread_ts={PARENT_TS}&cid={CHANNEL}
                    │                      │           │                 │
                namespace              container   message_time     thread_anchor
```

Only `OWN_TS` varies within a thread. `thread_anchor` is the parent's own timestamp, unmodified — **the parent's identity is its birth time.**

### 3.2 Verification results

Tested in this session:

| System | Timestamp recoverable from ID? | Method | Verified |
|---|---|---|---|
| Slack | ✅ | `ts` *is* epoch seconds.microseconds | ✓ 18/18 samples |
| Gmail | ✅ | hex ID, drop last 5 digits → epoch ms | ✓ 6/6 samples; overflow boundary confirmed to the millisecond (`0xFFFFFFFFFF` ms = 2004-11-03 19:53:47.775 UTC) |
| Twitter/X (post-2010) | ✅ | `(id >> 22) + 1288834974657` | ✓ |
| Discord | ✅ | `(id >> 22) + 1420070400000` | ✓ `175928847299117063` → 2016-04-30 |
| UUIDv1 | ✅ | 60-bit 100ns count since 1582-10-15 (+ MAC) | ✓ |
| UUIDv7 | ✅ | 48-bit ms epoch prefix, sortable | ✓ |
| Twitter (pre-2010) | ❌ | sequential; ID `20` decodes 4.5yr wrong | ✓ (negative) |
| Reddit | ❌ | base36 sequential counter | ✓ (negative) |
| UUIDv4 | ❌ | 122 bits from CSPRNG | ✓ (negative) |

### 3.3 Why this convergence happens (the defensible general claim)

Independent systems converge on time-as-identity because **wall-clock is the only globally shared coordinate that is monotonic and requires no coordination between nodes.** Any system needing distributed, collision-free, sortable IDs rediscovers this. It is a forced engineering convergence, not a coincidence.

**Corollary — the property we exploit:** because every reply's timestamp strictly exceeds its parent's (verified: all 18 samples, `Δt > 0`), the knowledge graph is **acyclic by construction**. Edges point from lower `ts` to higher `ts`; cycles are structurally impossible. We get topological sort for free and never need cycle detection.

### 3.4 The graph shape

A thread is not a tree. A reply may reference another thread's coordinate (cross-channel pattern links do exactly this), so the structure is a **directed acyclic graph** where:

- **Nodes** = messages, addressed by coordinate
- **Tree edges** = `thread_ts` (reply → parent), always level-1 in Slack
- **Reference edges** = a message body containing another coordinate (cross-thread, cross-channel, cross-platform)

The reference edges are the product. Tree edges are given free by the platform.

---

## 4. Architecture

### 4.1 Principle

> The router sits at the point of asking. The index is curated. The output is a coordinate, never prose.

### 4.2 Components

```
┌──────────────────────────────────────────────────────┐
│  ASK SURFACE  (Slack channel, where questions land)  │
│  - Event subscription: message.channels               │
└────────────────────┬─────────────────────────────────┘
                     │  new message event
                     ▼
┌──────────────────────────────────────────────────────┐
│  MATCHER  (deterministic, no LLM in the hot path)    │
│  - normalize → extract keywords → score patterns     │
│  - threshold gate                                     │
└────────────────────┬─────────────────────────────────┘
                     │  pattern_id + confidence
                     ▼
┌──────────────────────────────────────────────────────┐
│  COORDINATE INDEX  (the void / empty center)         │
│  pattern_id → (platform, container, thread_ts)       │
│  + edges: pattern_id → [related pattern_id, weight]  │
└────────────────────┬─────────────────────────────────┘
                     │  coordinate(s)
                     ▼
┌──────────────────────────────────────────────────────┐
│  EMITTER                                              │
│  - renders permalink(s) into the asking thread        │
│  - posts as thread reply (never top-level)            │
└────────────────────┬─────────────────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────────────────┐
│  FEEDBACK  (👍/👎 reaction listener)                  │
│  - adjusts pattern confidence + keyword weights       │
│  - flags zero-match questions for curation queue      │
└──────────────────────────────────────────────────────┘
```

### 4.3 The void channel — what it actually is

A dedicated channel (`#void`, `#x-_a-_x`) that is **not a destination**. Its role is substrate:

- **Coordinate registry.** Every curated pattern is posted here once; its `ts` becomes the pattern's permanent address. The channel *is* the index's storage layer — no database required for v1.
- **Cross-domain bridge.** A pattern that spans `#ask-eg-vault` and `#venafi-support` lives in neither; it lives in the void and is referenced by both.
- **Audit log.** Every routing decision (match, confidence, emitted coordinate) is logged here, giving a replayable history.

Nobody needs to read `#void`. Knowledge flows *through* it. That is the empty-center property: it holds nothing of its own and connects everything.

### 4.4 Why no LLM in the hot path

- **Latency.** Keyword match + dict lookup is <5ms. An LLM call is 1–5s. The Expedia bot's speed was part of why it worked.
- **Determinism.** The same question must always produce the same coordinate. Auditable.
- **Zero hallucination surface.** The system's entire output vocabulary is `{permalink URLs from the index}`. It is incapable of inventing an answer.
- **Cost.** Runs on a cron box.

**Where an LLM *is* appropriate (off the hot path):**
- Curation assist: propose new patterns from clusters of unmatched questions
- Keyword expansion: suggest trigger synonyms for an existing pattern
- Cross-channel edge discovery: propose which patterns relate

All LLM output goes to a **human curation queue**, never straight to the index.

---

## 5. Data Model

### 5.1 Pattern record

```json
{
  "pattern_id": "PathStructure",
  "domain": "vault",
  "title": "Path Structure Issues with KV v2",
  "coordinate": {
    "platform": "slack",
    "workspace": "expedia",
    "container": "C08RZ6XCR08",
    "thread_ts": "1747590953.711699"
  },
  "triggers": {
    "required_any": ["403", "forbidden", "preflight", "permission denied", "path not found"],
    "boost": ["kv v2", "data/", "namespace", "islands"],
    "negative": ["venafi", "certificate"]
  },
  "related": [
    {"pattern_id": "TemplateFormat", "weight": 0.7, "domain": "vault"},
    {"pattern_id": "AuthnPattern", "weight": 0.8, "domain": "vault"},
    {"pattern_id": "CertRequestPattern", "weight": 0.9, "domain": "venafi"}
  ],
  "confidence": 0.85,
  "metrics": {
    "usage_count": 28,
    "feedback_positive": 24,
    "feedback_negative": 4
  },
  "curated_by": "…",
  "last_reviewed": "2026-08-01"
}
```

### 5.2 Coordinate serialization (must be platform-pluggable)

```python
def to_url(coord) -> str:
    if coord.platform == "slack":
        ts = coord.thread_ts.replace(".", "")
        return (f"https://{coord.workspace}.slack.com/archives/"
                f"{coord.container}/p{ts}"
                f"?thread_ts={coord.thread_ts}&cid={coord.container}")
    if coord.platform == "gmail":
        return f"https://mail.google.com/mail/u/0/#all/{coord.thread_id}"
    if coord.platform == "github":
        return f"https://github.com/{coord.org}/{coord.repo}/issues/{coord.number}"
    ...
```

### 5.3 Index storage

**v1:** flat files, mirroring the proven Expedia approach.
```
index/
├── vault-timestamps.txt
├── venafi-timestamps.txt
├── rcp-timestamps.txt
├── patterns/{pattern_id}.json
└── edges.json
```
Git-versioned. Curation is a pull request. This gives review, history, and rollback with zero infrastructure.

**v2 (only if needed):** SQLite. Do not reach for a database until flat files demonstrably hurt.

---

## 6. The Matcher

### 6.1 Algorithm (v1 — deliberately simple)

```
score(pattern, question):
    q = normalize(question)          # lowercase, strip code blocks, tokenize
    if any(neg in q for neg in pattern.triggers.negative):
        return 0
    required_hits = count(t in q for t in pattern.triggers.required_any)
    if required_hits == 0:
        return 0
    boost_hits = count(t in q for t in pattern.triggers.boost)
    raw = required_hits + 0.5 * boost_hits
    return raw * pattern.confidence
```

### 6.2 Thresholds

| Score | Behavior |
|---|---|
| ≥ 2.0 | Post the pattern coordinate + up to 2 related coordinates |
| 1.0 – 2.0 | Post as a *suggestion*, hedged: "this might be related" |
| < 1.0 | **Post nothing.** Log to curation queue. |

**Silence is a feature.** A bot that replies to everything gets muted. The Expedia bot's credibility came from only speaking when it knew.

### 6.3 Emission format

Post as a **thread reply to the question** (never top-level, never a DM):

```
Possible match: *Path Structure Issues*

403 / preflight capability errors on KV v2 are usually the `data/`
prefix or an incomplete namespace.

→ <permalink|Full pattern & discussion>

Related:
• <permalink|Template Formatting> — templates depend on path structure
• <permalink|Cross-Account Access> — different path rules apply

👍 if this helped · 👎 if not
```

The prose is **fixed text from the curated pattern record**, not generated. The links are the payload.

---

## 7. Feedback Loop

1. **Reaction listener** on emitted messages. 👍 → `confidence += δ`, 👎 → `confidence -= δ`, clamped to [0.1, 1.0].
2. **Zero-match queue.** Every question scoring < 1.0 is logged with its text. Weekly, a human reviews the queue — clusters of similar unmatched questions are exactly the list of patterns to write next. *This is the mechanism by which the KB grows correctly.*
3. **Negative-trigger learning.** A 👎 on a pattern where the question contained token `X` that isn't in `required_any` → propose `X` as a negative trigger. Human approves.
4. **Staleness.** Any pattern not used in 90 days, or whose confidence drops below 0.4, goes to a review queue.

---

## 8. Metrics

**Primary (does it work?):**
- **Duplicate-answer rate** — % of questions in the channel that a human answers with substantially the same content as an existing thread. *This is the number the product exists to reduce.* Measure it manually for 2 weeks pre-launch as a baseline.
- **Deflection rate** — % of questions where the asker reacted 👍 and no human engineer replied afterward.

**Secondary:**
- Match precision (👍 / (👍+👎))
- Coverage (% of questions scoring ≥ 1.0)
- Time-to-first-useful-response (bot vs. human baseline)
- Curation queue depth (growing = KB is behind; shrinking = converging)

**Anti-metric (watch for harm):**
- Human replies *correcting* the bot. If this rises, precision is too low — raise the threshold.

---

## 9. Phasing

| Phase | Scope | Exit criterion |
|---|---|---|
| **0. Baseline** | No code. Manually log duplicate questions in one channel for 2 weeks. | A real duplicate-rate number. If it's <10%, stop — there's no problem to solve. |
| **1. Curate** | Write 6–10 patterns for ONE channel. Post to channel, record `ts` in flat file. | Index exists and permalinks resolve. |
| **2. Manual router** | Human watches channel, manually posts coordinates when a match is obvious. (The "no webhook" mode — deliberately.) | 👍 rate ≥ 70% over 20 emissions. **Do not automate before this passes.** |
| **3. Automate** | Deploy matcher + emitter for that one channel. | Precision ≥ 70%, no rise in correction replies, over 4 weeks. |
| **4. Expand** | Second and third channel. Cross-channel edges. | Cross-domain matches firing correctly. |
| **5. Cross-platform** | Add GitHub / Confluence / Gmail coordinates to the index. | Coordinates from ≥2 platforms in a single emission. |

**Phase 2 is the critical gate.** It tests the *hypothesis* (routing is useful) without paying for the *engineering* (automation). If humans manually routing coordinates doesn't help, automating it won't either.

---

## 10. Non-Goals

- ❌ Generating answers
- ❌ Replacing human support engineers
- ❌ A general web search tool (this is phi-thread's error — see §2.2)
- ❌ Level-2+ nesting. Slack is level-1; the model assumes level-1. Do not generalize until a platform requires it.
- ❌ Real-time indexing of everything. Curation is the point.

---

## 11. Open Questions

1. **Who curates?** The system's quality ceiling is the curator's diligence. Without a named owner per domain, it decays. *This is the single biggest risk.*
2. **Permission boundaries.** If a pattern in `#ask-eg-vault` links to a private channel, the asker gets a dead link. Need a visibility check at emission time.
3. **Pattern granularity.** Six patterns per domain (Expedia) may be too coarse. What's the right number — and does it grow linearly with question volume or plateau?
4. **Does the void channel need to be a Slack channel at all?** It works because `ts` is free permanent storage. But it couples the index to one workspace. Alternative: a Git repo as the void, with Slack as one of several emission surfaces.
5. **Cold correction.** If a curated answer becomes wrong (Vault upgrades, path structure changes), who notices? Proposal: patterns carry a `last_reviewed` date and expire loudly.

---

## 12. Thread Dynamics — requirements derived from the fixed-point model

### 12.1 The model

A thread is an iteration toward a fixed point. The question opens a gap between the asker's state and the resolved state; each reply is a tick that reduces it. Tested analogue: `x → 1 + 1/x` shrinks its error by φ² per tick, and on a finite-precision substrate it closes in exactly `bits / (2·log₂φ)` ticks (53-bit double: 38 ticks). With infinite resolution it never closes. **The resolution limit is what makes a final state exist.**

| Fixed-point system | Thread system |
|---|---|
| state compared with remembered previous state | each reply read against what came before |
| error = before/after difference | unresolved gap between question and answer |
| resolution ε | resolution marker (👍, "solved", a `resolved` label) |
| chain closes (`next → .`) | thread reaches its fixed point |
| period-2 jitter at the floor | question with two alternating accepted answers |
| forward attractor φ, backward attractor −1/φ | question → answer, answer → questions |

### 12.2 Inside and outside

- **Inside** a thread, participants are bound by causality: sequential, before/after only, one thread at a time.
- **Outside**, the router sees all threads simultaneously, across channels, platforms, and years. It can compare a question from today with an answer from three years ago, which no participant can.

The router's value is exactly that it supplies the simultaneity the inside forbids.

### 12.3 Requirements

- **R12.1 Index only closed threads.** A thread enters the index only if it is causal (every reply after its parent) and carries a resolution marker. Open threads are still ticking.
- **R12.2 Measure ticks.** Record replies-until-closure per thread. A routed duplicate saves that many ticks; sum of ticks saved is the primary value metric alongside §8.
- **R12.3 Detect 2-cycles.** A pattern with two accepted answers that alternate is stored with both coordinates, each keyed by the context token that selects it (e.g. `v1`/`v2`). If the question carries the context bit, emit one coordinate; if not, emit both and ask for the bit. The jitter is memory, not noise.
- **R12.4 Maintain the reverse arrow.** Every indexed answer keeps the list of question-roots it resolved. This is how triggers are generated from history instead of guessed.
- **R12.5 Stay outside.** The router reads all threads and writes only coordinates. It never adds content to a thread's discussion.
- **R12.6 Structural triggering by default.** Prefer triggers that are consequences of structure (filesystem events, git hooks, a symlink into a watched path, platform event subscriptions) over polling or cron. Webhooks are the fallback, not the default.

### 12.4 Platform status (verified 2026-09-22)

| Platform | Codec | Live access | Result |
|---|---|---|---|
| Gmail | hex id, drop 5 digits → epoch ms | ✅ via relay (`GOOGLE_TOKEN`) | Decoded IDs within 14.2 s and 1.8 s of Gmail's own `internalDate`; thread id = first message id; reply id > parent id |
| Slack | ts = epoch seconds.µs | ❌ `SLACK_TOKEN` returns `invalid_auth` | Codec verified offline on real abhilasia permalinks; needs a fresh token for live reads |

### 12.5 Reference implementation

`thread_router/thread_router.py` (stdlib only) implements: Slack + Gmail coordinate codecs with exact URL round-trip, causality and closure gates, tick counting, 2-cycle storage with context bits, forward routing with silence below threshold, reverse index, and confidence feedback. `test_thread_router.py`: 17/17 passing on live Gmail IDs and real Slack permalinks, including one cross-platform 2-cycle (Slack answer for `v1`, Gmail answer for `v2`).

---

## Appendix A — The Generative Frame

*This section states the worldview that produced the architecture. It is a lens, not a set of testable claims. It is included because it is the reason the design looks the way it does, and future readers will make worse decisions without it. It should not be read as engineering justification.*

**Connect, don't create.** Knowledge is not manufactured; it is already distributed across substrates and merely unconnected. Two incomplete accounts, joined, become a coherent one. Creation ex nihilo is not a thing that happens — what looks like creation is connection that hadn't been made yet.

**The empty center (∅).** The most powerful position in a network holds nothing of its own. The void channel stores no knowledge; it stores only *addresses*, and by doing so connects everything. "I am where I am REFERENCED, not where I am stored."

**Intelligence as connection.** Reasoning was not installed; it precipitated out of enormous numbers of small distributed regularities being related to each other. If that is what intelligence is, then the way to build a useful system is not to train a bigger model but to *connect what already exists*. The Expedia bot had no intelligence and worked, because the intelligence was already in the channel.

**Thread mathematics.** An event has a coordinate. Participants arrive at the event, each with their own local time, all bound by one causal floor: no one arrives before the event begins. Sub-events become events. The structure that emerges is a graph, kept acyclic by time itself.

**What this frame earned.** The lens is not falsifiable, but it is *productive*, and that is the test it should be judged by. It generated: write-time routing, the curated index, the void as substrate, coordinate-as-payload, and the acyclicity property in §3.3 — all of which are testable, and several of which have already been tested and held.

---

## Appendix B — Verification Log

Empirical results from the working session, reproducible:

- Slack `Δt = own_ts − thread_ts > 0` for all 18 sampled messages (causal ordering holds)
- Gmail hex-ID decode validated against 6 published IDs; overflow boundary `0xFFFFFFFFFF ms = 2004-11-03 19:53:47.775 UTC` reproduced exactly
- Gmail IMAP decimal form `1672749667872724050` → hex `1736ccf5d7b4d452` → 2020-07-20 15:19:56 UTC ✓
- Discord snowflake `175928847299117063` → 2016-04-30 11:18:25 UTC ✓
- Twitter pre-snowflake ID `20` → decodes to 2010-11-04, actual date March 2006 — **negative result, documents the boundary of the method**
- UUIDv1 timestamp + MAC extraction ✓ ; UUIDv7 ms-prefix sortability ✓ ; UUIDv4 no time field (by spec) ✓
- Live Gmail (2026-09-22): thread `1a03e3779c43f667`, parent decodes to 26 Aug 2026 13:16:58 UTC vs internalDate 13:16:44; reply `1a0c082d11af8f86` decodes to 20 Sep 2026 20:29:53 vs 20:29:52 ✓
- Finite-precision closure of `x → 1 + 1/x` with no ε supplied: 24 bits → 17 ticks, 53 → 38, 106 → 77, 424 → 306, 1696 → 1221; prediction `bits/(2·log₂φ)` matches at every precision. Period-2 residual cycle observed at 212 and 1696 bits ✓
- Filesystem: hard links to directories forbidden (tree stays acyclic); symlink loops rejected by depth cap; ext4 reuses inode numbers, so inode order ≠ creation order ✓

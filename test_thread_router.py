"""Run: python3 test_thread_router.py
Gmail fixtures are real IDs + internalDate values fetched live on 2026-09-22 (no content).
Slack fixtures are the abhilasia permalinks from the design conversation."""
from thread_router import Coord, Message, Thread, Index, parse

ok = lambda cond, msg: print(("PASS " if cond else "FAIL ") + msg) or cond
results = []

# ---- 1. Gmail: decoded ID time vs Gmail's own internalDate (live data) ----
live = [("1a03e3779c43f667", 1787750204000), ("1a0c082d11af8f86", 1789936192000)]
for mid, internal in live:
    c = Coord("gmail", "0", "1a03e3779c43f667", mid)
    results.append(ok(abs(c.epoch_ms() - internal) < 60_000,
                      f"gmail {mid} decodes within 60s of internalDate ({c.epoch_ms()-internal} ms)"))

# ---- 2. Slack: parse/url round trip, parent vs reply ----
parent_url = "https://abhilasia.slack.com/archives/C0999BRDDAM/p1760400744994749"
reply_url = ("https://abhilasia.slack.com/archives/C0999BRDDAM/p1761930161842119"
             "?thread_ts=1760400744.994749&cid=C0999BRDDAM")
p, r = parse(parent_url), parse(reply_url)
results.append(ok(p.is_parent() and not r.is_parent(), "slack parent/reply identified"))
results.append(ok(p.url() == parent_url and r.url() == reply_url, "slack url round trip exact"))
results.append(ok(r.thread == p.message, "reply carries parent identity (thread_ts)"))
results.append(ok(str(r.when())[:16] == "2025-10-31 17:02", "slack reply time = 31 Oct 2025 17:02 UTC"))

# ---- 3. Causality + closure gate the index ----
gmail_thread = Thread([
    Message(Coord("gmail", "0", "1a03e3779c43f667", "1a03e3779c43f667"), "question"),
    Message(Coord("gmail", "0", "1a03e3779c43f667", "1a0c082d11af8f86"), "Done.", resolved_marker=True),
])
results.append(ok(gmail_thread.causal(), "live gmail thread is causal"))
results.append(ok(gmail_thread.closed() and gmail_thread.ticks() == 1, "closed, 1 tick to fixed point"))

open_thread = Thread([Message(p, "q"), Message(r, "still discussing")])
idx = Index()
try:
    idx.add_closed("X", open_thread, {"x"}); results.append(ok(False, "open thread rejected"))
except ValueError:
    results.append(ok(True, "open thread rejected from index"))

acausal = Thread([Message(r, "q"), Message(p, "answer", resolved_marker=True)])
try:
    idx.add_closed("Y", acausal, {"y"}); results.append(ok(False, "acausal rejected"))
except ValueError:
    results.append(ok(True, "acausal thread rejected (reply before parent)"))

# ---- 4. Routing, silence, cross-platform ----
slack_closed = Thread([Message(p, "403 on kv"), Message(r, "use data/ prefix", resolved_marker=True)])
idx.add_closed("PathStructure", slack_closed, {"403", "forbidden", "preflight"},
               boost={"kv", "data/"}, negative={"venafi"})
out = idx.route("getting 403 forbidden on kv read")
results.append(ok(out["action"] == "route" and out["coords"] == [reply_url], "question routed to answer coordinate"))
results.append(ok(idx.route("venafi cert 403")["action"] == "silent", "negative trigger -> silence"))
results.append(ok(idx.route("how do i bake bread")["action"] == "silent", "no match -> silence"))

# ---- 5. 2-cycle: two alternating accepted answers + context bit ----
v1 = Coord("slack", "C0999BRDDAM", "1760400744.994749", "1760404344.770487", "abhilasia")
v2 = Coord("gmail", "0", "1a03e3779c43f667", "1a0c082d11af8f86")
idx.add_closed("KVVersion", Thread([Message(p, "q"), Message(v1, "v1 fix", True)]),
               {"kv", "secret", "missing"}, context="v1")
idx.add_closed("KVVersion", Thread([Message(v2.__class__("gmail", "0", v2.thread, v2.thread), "q"),
                                    Message(v2, "v2 fix", True)]),
               {"kv", "secret", "missing"}, context="v2")
results.append(ok(idx.is_two_cycle("KVVersion"), "2-cycle detected (two accepted answers)"))
both = idx.route("kv secret missing")
results.append(ok(both["context_bit_needed"] and len(both["coords"]) == 2, "no context bit -> both coords, ask for the bit"))
one = idx.route("kv secret missing on v2")
results.append(ok(not one["context_bit_needed"] and one["coords"] == [v2.url()], "context bit present -> one coord (cross-platform)"))

# ---- 6. Reverse arrow ----
results.append(ok(idx.reverse[r] == [p], "reverse index: answer -> question it resolved"))

# ---- 7. Regressions ----
results.append(ok(idx.route("getting 403 forbidden on kv.")["action"] == "route",
                  "sentence-final punctuation does not break a match"))
idx.add_closed("Preflight", Thread([Message(p, "q"), Message(r, "a", True)]), {"permission denied", "cors"})
pd = idx.route("permission denied by cors")
results.append(ok(pd["action"] != "silent" and pd["pattern"] == "Preflight", "multi-word trigger matches as a phrase"))
results.append(ok(idx.route("denied permission by cors")["score"] < pd["score"], "phrase needs its words in order"))
ans = Coord("slack", "C0999BRDDAM", "1760400744.994749", "1760404344.770487", "abhilasia")
t = Thread([Message(p, "403 on kv v2"), Message(ans, "use the data/ prefix"), Message(r, "thanks, solved!", True)])
results.append(ok(t.answer() == ans and t.ticks() == 1, "marker on 'thanks' -> answer is the reply before it"))
t2 = Thread([Message(p, "403 on kv v2", True), Message(ans, "use the data/ prefix")])
results.append(ok(t2.answer() == ans and t2.ticks() == 1, "marker on the question -> answer is the reply"))
results.append(ok(not Thread([Message(p, "q", True)]).closed(), "marker on a lone question is not a closed thread"))

print(f"\n{sum(results)}/{len(results)} passed")

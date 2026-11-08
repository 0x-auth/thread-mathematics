"""thread_router — route questions to the coordinates of already-closed threads.

Principles (PRD §3, §12):
  * A message's identity is its birth time. Coordinates are decodable to time.
  * Only closed threads (fixed point reached, resolution marker present) are indexed.
  * The router is outside every thread: it reads all, writes only coordinates.
  * Two arrows: question -> coordinate (forward), coordinate -> questions (reverse).
  * Recurring questions with two alternating accepted answers are a 2-cycle:
    keep both coordinates plus the context bit that selects between them.
Stdlib only.
"""
from __future__ import annotations
import datetime as _dt
import re
from collections import defaultdict
from dataclasses import dataclass, field


# ---------------------------------------------------------------- coordinates
@dataclass(frozen=True)
class Coord:
    platform: str          # "slack" | "gmail"
    container: str         # slack channel id | gmail account index ("0")
    thread: str            # slack thread_ts | gmail thread id (hex)
    message: str           # slack own ts   | gmail message id (hex)
    workspace: str = ""    # slack only

    # identity is birth time --------------------------------------------
    def epoch_ms(self) -> int:
        if self.platform == "slack":
            return int(round(float(self.message) * 1000))
        if self.platform == "gmail":
            return int(self.message[:-5], 16)          # drop 5 hex digits
        raise ValueError(self.platform)

    def when(self) -> _dt.datetime:
        return _dt.datetime.fromtimestamp(self.epoch_ms() / 1000, tz=_dt.timezone.utc)

    def is_parent(self) -> bool:
        return self.thread == self.message

    def url(self) -> str:
        if self.platform == "slack":
            p = self.message.replace(".", "")
            base = f"https://{self.workspace}.slack.com/archives/{self.container}/p{p}"
            return base if self.is_parent() else \
                f"{base}?thread_ts={self.thread}&cid={self.container}"
        if self.platform == "gmail":
            return f"https://mail.google.com/mail/u/{self.container}/#all/{self.thread}"
        raise ValueError(self.platform)


_SLACK_RE = re.compile(
    r"https://(?P<ws>[\w-]+)\.slack\.com/archives/(?P<ch>\w+)/p(?P<p>\d{16})"
    r"(?:\?thread_ts=(?P<tts>\d+\.\d+))?")
_GMAIL_RE = re.compile(r"https://mail\.google\.com/mail/u/(?P<u>\d+)/#\w+/(?P<id>[0-9a-f]{15,16})")


def parse(url: str) -> Coord:
    if m := _SLACK_RE.match(url):
        own = f"{m['p'][:10]}.{m['p'][10:]}"
        return Coord("slack", m["ch"], m["tts"] or own, own, m["ws"])
    if m := _GMAIL_RE.match(url):
        return Coord("gmail", m["u"], m["id"], m["id"])
    raise ValueError(f"not a thread coordinate: {url}")


# --------------------------------------------------------------------- thread
@dataclass
class Message:
    coord: Coord
    text: str = ""
    resolved_marker: bool = False      # 👍 / "solved" / resolved label = the thread's ε


@dataclass
class Thread:
    messages: list[Message]

    @property
    def root(self) -> Coord:
        return self.messages[0].coord

    def causal(self) -> bool:
        """Every reply strictly after its parent: the arrow the index relies on."""
        t0 = self.root.epoch_ms()
        return all(m.coord.epoch_ms() > t0 for m in self.messages[1:])

    def _marker_index(self) -> int | None:
        for i, m in enumerate(self.messages):
            if m.resolved_marker:
                return i
        return None

    def _answer_index(self) -> int | None:
        """The marker closes the thread; the answer is the reply it confirms.
        A marker on a bare acknowledgment ("thanks, solved") or on the question
        itself (asker reacts on their own post) confirms the latest real reply
        before it, or the last reply when the root carries the marker."""
        k = self._marker_index()
        if k is None:
            return None
        if k == 0:                                   # marker on the question
            return len(self.messages) - 1 if len(self.messages) > 1 else None
        i = k
        while i > 0 and _is_ack(self.messages[i].text):
            i -= 1
        return i if i > 0 else k

    def closed(self) -> bool:
        """Fixed point reached: a resolution marker exists and confirms a reply."""
        return self._answer_index() is not None

    def ticks(self) -> int:
        """Replies until the answer = the work a routed duplicate saves."""
        a = self._answer_index()
        return a if a is not None else len(self.messages) - 1

    def answer(self) -> Coord | None:
        a = self._answer_index()
        return self.messages[a].coord if a is not None else None


_ACK = re.compile(r"^\W*(thanks?|thank you|thx|ty|solved|fixed|resolved|works?|worked|"
                  r"that worked|done|perfect|great|got it|ok(ay)?)\b[\w\s,.!👍✅🙏]*$", re.I)

def _is_ack(text: str) -> bool:
    t = (text or "").strip()
    return bool(t) and len(t) <= 40 and bool(_ACK.match(t))


# ---------------------------------------------------------------------- index
def _tokens(s: str) -> set[str]:
    # sentence punctuation is not part of a token: "kv." -> "kv", "data/." -> "data/"
    return {t.rstrip(".-") for t in re.findall(r"[a-z0-9][a-z0-9._/-]+", s.lower())} - {""}


def _hits(q: set[str], qtext: str, terms: set[str]) -> int:
    """Single-word terms match tokens; multi-word terms match as a phrase."""
    n = 0
    for t in terms:
        if " " in t:
            n += f" {' '.join(t.lower().split())} " in qtext
        else:
            n += t in q
    return n


def _phrase_text(s: str) -> str:
    words = [w.rstrip(".-") for w in re.findall(r"[a-z0-9][a-z0-9._/-]*", s.lower())]
    return " " + " ".join(w for w in words if w) + " "


@dataclass
class Pattern:
    pid: str
    triggers: set[str]
    boost: set[str] = field(default_factory=set)
    negative: set[str] = field(default_factory=set)
    # one answer normally; two for a 2-cycle, keyed by the context token that selects it
    answers: dict[str, Coord] = field(default_factory=dict)
    confidence: float = 0.8
    ticks_saved_each: int = 0


class Index:
    def __init__(self):
        self.patterns: dict[str, Pattern] = {}
        self.reverse: dict[Coord, list[Coord]] = defaultdict(list)   # answer -> questions

    def add_closed(self, pid: str, thread: Thread, triggers, boost=(), negative=(),
                   context: str = "default"):
        if not thread.causal():
            raise ValueError("acausal thread: a reply predates its parent")
        if not thread.closed():
            raise ValueError("open thread: still ticking, not indexable")
        p = self.patterns.setdefault(pid, Pattern(pid, set(triggers)))
        p.triggers |= set(triggers); p.boost |= set(boost); p.negative |= set(negative)
        p.answers[context] = thread.answer()
        p.ticks_saved_each = max(p.ticks_saved_each, thread.ticks())
        self.reverse[thread.answer()].append(thread.root)

    def is_two_cycle(self, pid: str) -> bool:
        return len(self.patterns[pid].answers) == 2

    # -------------------------------------------------------------- router
    def route(self, question: str, hi: float = 2.0, lo: float = 1.0) -> dict:
        q = _tokens(question)
        qtext = _phrase_text(question)
        best, best_score = None, 0.0
        for p in self.patterns.values():
            if _hits(q, qtext, p.negative):
                continue
            req = _hits(q, qtext, p.triggers)
            if not req:
                continue
            score = (req + 0.5 * _hits(q, qtext, p.boost)) * p.confidence
            if score > best_score:
                best, best_score = p, score
        if not best or best_score < lo:
            return {"action": "silent", "score": best_score}          # silence is a feature
        # 2-cycle: pick by context bit if present in the question, else return both
        chosen = {c: a for c, a in best.answers.items() if c in q} or best.answers
        return {
            "action": "route" if best_score >= hi else "suggest",
            "pattern": best.pid,
            "score": round(best_score, 2),
            "coords": [a.url() for a in chosen.values()],
            "two_cycle": len(best.answers) == 2,
            "context_bit_needed": len(best.answers) == 2 and len(chosen) == 2,
            "ticks_saved": best.ticks_saved_each,
        }

    def feedback(self, pid: str, positive: bool, delta: float = 0.05):
        p = self.patterns[pid]
        p.confidence = min(1.0, max(0.1, p.confidence + (delta if positive else -delta)))

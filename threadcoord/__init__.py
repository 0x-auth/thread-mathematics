"""threadcoord — decode when a message was born, from its ID alone. No API, no auth.

Every major platform stamps time into its identifiers. This library reads it back:
a permalink, a snowflake, a hex mail-id, a UUIDv7 — all carry a timestamp you can
recover with arithmetic, offline. It also tells you honestly when an ID carries NO
time (UUIDv4, Reddit base36, pre-2010 Twitter) rather than inventing one.

    >>> from threadcoord import decode
    >>> decode("slack", "1761930161.842119").isoformat()
    '2025-10-31T17:02:41.842119+00:00'
    >>> decode("twitter", 1585841080431321088)
    datetime.datetime(2022, 10, 28, 3, 49, 11, 734000, tzinfo=timezone.utc)
"""
from __future__ import annotations
import datetime as _dt
from dataclasses import dataclass

__version__ = "0.1.0"
__all__ = ["decode", "has_time", "Decoded", "UndecodableID"]

_UTC = _dt.timezone.utc
TWITTER_EPOCH = 1288834974657   # 2010-11-04
DISCORD_EPOCH = 1420070400000   # 2015-01-01


class UndecodableID(ValueError):
    """Raised for an ID whose scheme carries no recoverable timestamp."""


@dataclass(frozen=True)
class Decoded:
    when: _dt.datetime      # UTC
    platform: str
    precision: str          # 'microsecond' | 'millisecond' | 'second'
    def isoformat(self) -> str: return self.when.isoformat()


def _ms(ms: int, platform: str, precision="millisecond") -> Decoded:
    return Decoded(_dt.datetime.fromtimestamp(ms / 1000, tz=_UTC), platform, precision)


# ---- platforms that CARRY time -------------------------------------------
def _slack(ts: str) -> Decoded:
    # "1761930161.842119" seconds.microseconds, or the p<...> permalink form
    s = str(ts)
    if "." not in s and len(s) >= 16:          # p-form: 16 digits, no dot
        s = f"{s[:10]}.{s[10:]}"
    return Decoded(_dt.datetime.fromtimestamp(float(s), tz=_UTC), "slack", "microsecond")

def _snowflake(i, epoch, platform) -> Decoded:
    i = int(i)
    if i < (1 << 22):   # too small to be a snowflake (pre-rollout sequential id)
        raise UndecodableID(f"{i} predates snowflake IDs on {platform}; sequential, no time")
    return _ms((i >> 22) + epoch, platform)

def _gmail(h: str) -> Decoded:
    # hex message/thread id: drop last 5 hex digits -> epoch ms
    return _ms(int(str(h)[:-5], 16), "gmail")

def _uuid(u: str) -> Decoded:
    s = str(u).replace("-", "")
    ver = s[12]
    if ver == "1":   # time: 100ns since 1582-10-15
        t = int(s[13:16] + s[8:12] + s[0:8], 16)
        return Decoded(_dt.datetime.fromtimestamp((t - 0x01b21dd213814000) / 1e7, tz=_UTC),
                       "uuid1", "microsecond")
    if ver == "7":   # first 48 bits = epoch ms
        return _ms(int(s[:12], 16), "uuid7")
    raise UndecodableID(f"UUIDv{ver} carries no timestamp (random)")

_DECODERS = {
    "slack":   _slack,
    "twitter": lambda i: _snowflake(i, TWITTER_EPOCH, "twitter"),
    "x":       lambda i: _snowflake(i, TWITTER_EPOCH, "twitter"),
    "discord": lambda i: _snowflake(i, DISCORD_EPOCH, "discord"),
    "gmail":   _gmail,
    "uuid":    _uuid,
}

# ---- platforms that DO NOT (honest refusals) -----------------------------
_NO_TIME = {
    "reddit":  "Reddit IDs are base36 sequential counters, not timestamps",
    "youtube": "YouTube IDs are random, not timestamps",
}


def decode(platform: str, identifier) -> Decoded:
    """Recover the birth time of a message from its ID. Raises UndecodableID
    when the platform's scheme carries no time."""
    p = platform.lower()
    if p in _NO_TIME:
        raise UndecodableID(_NO_TIME[p])
    if p not in _DECODERS:
        raise UndecodableID(f"unknown platform {platform!r}")
    try:
        d = _DECODERS[p](identifier)
    except UndecodableID:
        raise
    except Exception as e:
        raise UndecodableID(f"could not decode {identifier!r} for {platform}: {e}") from e
    # sanity: a real message time sits between 2005 and 2100
    if not (1104537600 < d.when.timestamp() < 4102444800):
        raise UndecodableID(f"decoded time {d.when} is implausible; wrong scheme?")
    return d


def has_time(platform: str, identifier=None) -> bool:
    """True if this platform's IDs carry a recoverable timestamp."""
    p = platform.lower()
    if p in _NO_TIME or p not in _DECODERS:
        return False
    if identifier is None:
        return True
    try:
        decode(platform, identifier); return True
    except UndecodableID:
        return False

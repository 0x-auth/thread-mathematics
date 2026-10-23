# threadcoord

Decode **when a message was born** from its ID alone — no API call, no auth, pure arithmetic.

Every major platform stamps time into its identifiers. `threadcoord` reads it back, and —
just as importantly — tells you honestly when an ID carries **no** time, instead of inventing one.

```python
from threadcoord import decode, has_time

decode("slack",   "1761930161.842119").isoformat()   # '2025-10-31T17:02:41.842119+00:00'
decode("twitter", 1585841080431321088)                # 2022-10-28 03:49:11 UTC
decode("discord", 175928847299117063)                 # 2016-04-30 11:18:25 UTC
decode("gmail",   "1a03e3779c43f667")                 # hex id -> creation time
decode("uuid",    "018f...-7...-...")                 # UUIDv7 -> epoch prefix
```

## What carries time, and what doesn't

| Platform | Carries time? | How |
|---|---|---|
| Slack | ✅ | `ts` is epoch seconds.microseconds (permalink `p<...>` form also accepted) |
| Twitter / X | ✅ (post-2010) | snowflake: `(id >> 22) + 1288834974657` |
| Discord | ✅ | snowflake: `(id >> 22) + 1420070400000` |
| Gmail | ✅ | hex message/thread id, drop last 5 hex digits → epoch ms |
| UUIDv1 | ✅ | 100 ns since 1582, embedded (+ MAC address) |
| UUIDv7 | ✅ | first 48 bits = epoch ms (sortable) |
| UUIDv4 | ❌ | 122 random bits — `UndecodableID` |
| Reddit | ❌ | base36 sequential counter — `UndecodableID` |
| Twitter pre-2010 | ❌ | sequential, not a snowflake — `UndecodableID` |

The honesty is the point: a timestamp is designed to be recovered; a random ID is designed
not to be. `threadcoord` recovers the first and refuses the second — it never fabricates a time.

```python
has_time("slack")                                    # True
has_time("reddit")                                   # False
has_time("uuid", "509a9263-2bf0-421b-9853-...")      # False  (v4)
```

## Why

A message ID is already a coordinate: it says *when*, often to the microsecond — finer than the
platform's own displayed timestamp. Two messages shown at the same second can be ordered by their
IDs. That makes IDs a join key across platforms with no API access at all.

## Install

```
pip install threadcoord
```

Zero dependencies. Python 3.8+.

## License

MIT

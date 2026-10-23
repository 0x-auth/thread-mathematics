import datetime as dt
from threadcoord import decode, has_time, UndecodableID

def ok(c,m): print(("PASS " if c else "FAIL ")+m); assert c
r=[]

# Slack: permalink p-form and dotted form, real abhilasia value
d=decode("slack","1761930161.842119"); ok(str(d.when)[:19]=="2025-10-31 17:02:41","slack dotted")
d=decode("slack","1761930161842119");  ok(str(d.when)[:19]=="2025-10-31 17:02:41","slack p-form (no dot)")

# Twitter: 'the bird is freed'
d=decode("twitter",1585841080431321088); ok(str(d.when)[:16]=="2022-10-28 03:49","twitter snowflake")
# Twitter from the real validated set, exact-to-second
d=decode("twitter",1984337721599701268); ok(str(d.when)[:19]=="2025-10-31 19:12:34","twitter real-set exact")

# Discord
d=decode("discord",175928847299117063); ok(str(d.when)[:10]=="2016-04-30","discord snowflake")

# Gmail hex (live-validated id)
d=decode("gmail","1a03e3779c43f667"); ok(d.when.year==2026 and d.when.month==8,"gmail hex decode")

# UUIDv7 round-trip
import os
ms=int(dt.datetime(2026,1,1,tzinfo=dt.timezone.utc).timestamp()*1000)
b=bytearray(ms.to_bytes(6,'big')+os.urandom(10)); b[6]=(b[6]&0x0F)|0x70; b[8]=(b[8]&0x3F)|0x80
import uuid; u=str(uuid.UUID(bytes=bytes(b)))
d=decode("uuid",u); ok(d.when.year==2026,"uuidv7 epoch prefix")

# honest refusals
for plat,idv,label in [("uuid","509a9263-2bf0-421b-9853-16b896d49a4b","uuidv4 refused"),
                       ("reddit","mkj0mru","reddit refused"),
                       ("twitter",20,"pre-2010 twitter implausible refused")]:
    try: decode(plat,idv); ok(False,label)
    except UndecodableID: ok(True,label)

ok(has_time("slack") and not has_time("reddit"),"has_time flags platforms")
ok(not has_time("uuid","509a9263-2bf0-421b-9853-16b896d49a4b"),"has_time false for v4")

print("\nall passed")

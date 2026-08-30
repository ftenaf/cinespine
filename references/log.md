---
type: log
title: What was learned, and when
description: Chronology of findings about this codebase, newest first
tags: [log]
---

# Log

Newest first. Each entry names what produced it.

## 2026-08-30

**Clearing the search box was hiding a wrong-array bug.** Deep-linking emptied the reader's query, which
the requirement forbids -- and the emptying was load-bearing: the jump computed an index into `takes` and
the navigator reads `filteredTakes`, so it only ever landed correctly because the filters had just been
cleared. Fixed by pinning the target by identity.

**The analytical mirror was write-only.** Every `SELECT` in the codebase went to SQLite while 5,090 events
sat in ClickHouse unread. The cost of writing was paid and none of the use taken. Fixed by
[the read path](architecture/analytical-mirror.md).

**A multi-camera take is not a disagreement.** The obvious disagreement query -- more than one roll for
this take -- returned rows immediately, and every one was a take shot on three cameras agreeing with
itself perfectly. Grouping by camera returns nothing on the demo day, which is the honest answer.

**A parsed fact can carry contact details.** A camera CSV row that was not a take at all left a contact
line in the `slate` field, reached the mirror, and surfaced in a scene grouping. See
[open questions](open-questions.md).

**Office documents reached no handler.** `production.raw.office` had no subscriber. A daily production
report ingested to zero events, zero takes and no dead-letter entry, while the upload answered
`INGESTED`. See [findings/defects-found.md](findings/defects-found.md).

**Source documents were served ungated.** Both document endpoints returned the original paperwork,
including a script supervisor's phone number and email. See [constraints/privacy.md](constraints/privacy.md).

**The shipped PII scrubber destroyed production data.** `A120 280726` came back as `A[REDACTED_PHONE]`:
a camera card and its shoot date read as a phone number.

**An audit against the design workspace found six gaps.** See [findings/spec-drift.md](findings/spec-drift.md).

## 2026-08-29

**A sequence shot over several days claimed to belong to one.** Scene 119 covered on day 11 and finished
on day 31 came back as two unrelated rows. Third instance of the same mistake; see
[domain/shoot-days.md](domain/shoot-days.md).

**Per-event durability was affordable.** Measured before choosing: 2,000 events cost 9.4s with a
connection per event and 0.06s on a held connection in WAL. See
[architecture/persistence.md](architecture/persistence.md).

**Requirements lost their history.** Creating and resolving reached the spine; every handover and block in
between was an in-place overwrite.

## 2026-08-28 and earlier

**Ingestion slowed 9x when every event was inserted to ClickHouse separately.** A 72-event document went
from 0.8s to 7.4s and a 1,991-event volume to over two minutes. Fixed by batching.

**A facing page carries takes from across the schedule.** It is filed on the day it is handed over, not
the day its takes were shot. First instance of the shoot-day mistake.

**Silence is not denial.** A lined page that does not mark a take as circled has not said it was
uncircled. Recorded as `None` rather than `false`.

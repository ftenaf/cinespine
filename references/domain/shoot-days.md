---
type: domain
title: A day is where paperwork arrives, not what a scene belongs to
description: The single domain fact this codebase has got wrong three times
tags: [domain, shoot-days, scenes]
status: confirmed
evidence: facing-page parser 2026-08-28; _project_analytics 2026-08-28; sequences matrix 2026-08-29
---

# A day is where paperwork arrives, not what a scene belongs to

This has now been got wrong three times, in three different places, by three different mechanisms. It is
the most reliable source of defects in the repository.

## What is actually true

- **A scene is covered over as many days as it takes.** The second half may be shot weeks after the first.
- **A document is filed on the day it is handed over**, and carries whatever it carries. A facing page is
  filed per scene and holds takes from across the schedule.
- So `shoot_day` on a *document* and `shoot_day` on a *take* are different facts, and the first must never
  be assumed onto the second.

## The three times

**1. The facing-page parser** assumed every row on a page belonged to the day the page was filed. A page
handed over on day 31 carried takes from days 11, 15, 18, 25, 30 and 31. Fixed by reading each row's own
date, and only falling back to the report's date when a row carries none.

**2. `_project_analytics`** projected only `envelope.shoot_day`, so sixty takes sat in the spine and never
reached the analytical index. Fixed by projecting every day the production has.

**3. The sequences matrix** grouped takes by the requested day and reported `shoot_day` as that day. A
scene covered on day 11 and finished on day 31 came back as two unrelated rows, each claiming to be the
whole sequence. Verified with a probe: scene 119, two takes on day 11 and one on day 31, no link between
them. Fixed by carrying `shoot_days` -- every day the sequence runs to -- while the row itself stays about
the day that was asked for.

## The check to run

Wherever `shoot_day` appears, ask whether it is being used as a **filter** or as an **identity**.

- As a filter -- "show me this day" -- it is fine.
- As an identity -- "this thing belongs to this day" -- it is probably wrong, unless the thing genuinely is
  a property of the day, like a call time or a wrap.

## The related sorting trap

Shoot days are strings and sort as strings. Day 9 comes after day 11 unless sorted numerically. Fixed in
the sequences matrix; worth checking anywhere days are ordered.

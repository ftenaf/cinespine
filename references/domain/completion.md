---
type: domain
title: "Complete" is a chain, not a state
description: What a scene being finished actually means, and how far the code represents it
tags: [domain, editorial, post-production]
status: confirmed
evidence: Francisco, 2026-08-30, answering references/open-questions.md
---

# "Complete" is a chain, not a state

A scene is completed in different contexts, in this order. Francisco's words, kept because a paraphrase
would lose the conditionals:

> * The script says it's fully shot.
> * Editor assistante mounted it.
> * Editor finish editing
> * The director sits down with the Editor and decides how to finish it. Once they are settled, they
>   prepare a "Picture Lock". This process could happen whenever the Director decides, sometimes in
>   specific scenes, sometimes when all scenes are edited.
> * Once they have a Picture Lock, they send it to Color, Sound (includes SFX), VFX.
> * VFX and SFX come back and forth and when they finished they do a "Conforming process".
> * After that they prepare the "DCP" (Digital Cinema Package)

## Why this matters more than it looks

"Is scene 27 complete?" has at least seven possible true answers, and which one is meant depends on who is
asking. A colourist and a script supervisor use the same word for different facts.

Picture lock is not a global milestone either. It happens **when the Director decides**, sometimes for one
scene and sometimes for all of them, so it cannot be modelled as a date the production passes through.

## What the code represents

The editorial tag vocabulary in `tag_store.py` now covers the whole chain. It stopped at the third step
until 2026-08-30:

| Francisco's step | Tag status | Ordinal |
|---|---|---|
| script says fully shot | `finished_shooting`, `covered_per_script` | 1, 2 |
| assistant mounted it | `ready_to_edit`, `mounted` | 3, 4 |
| editor finished editing | `finished` | 5 |
| picture lock | `picture_lock` | 6 |
| sent to colour / sound / VFX | `colour_sound_vfx` | 7 |
| conforming | `conformed` | 8 |
| DCP | `dcp` | 9 |

`needs` still carries `sfx` separately, and that is not a duplicate: the stage says where the coverage has
got to, the need says what is still owed on it. A scene can be at `colour_sound_vfx` and the interesting
question is which of the three has come back.

## What was wrong, and what it cost to fix

`finished` was described as "No further work expected", and it held the highest ordinal -- so a progress
bar showed a scene as complete with four stages still to come. It named the end of *editorial* as the end
of everything, which tells a colourist something untrue.

**The fix was additive, and this document previously said it would not be.** The earlier note reasoned
that statuses are stored on tags and mirrored to the trail, so changing the vocabulary meant a migration.
That was true of a *rename* and false of the actual problem. What was wrong with `finished` was never its
key: it was the label and the description, and those are vocabulary metadata that are never stored on a
tag. Correcting them and appending four stages after it changed no stored row.

Renaming would also have been wrong rather than merely expensive. `editorial_tag_events` is append-only,
so rewriting a status there would falsify what somebody recorded at the time -- and leaving the trail
alone while migrating the tags would leave the two copies disagreeing.

## What is still not represented

Picture lock is per coverage here, which matches "sometimes in specific scenes". What the model does not
carry is the *back and forth*: `colour_sound_vfx` is one stage, and colour, sound and VFX return
separately. If that distinction turns out to matter, three needs would express it better than three
statuses, because they are independent of each other and of how far along the coverage is.

## Related

The delivery chain beyond the cutting room is described in the design workspace at
`references/domain/dept-delivery-chain.md` and `dept-postproduction.md`. This document is narrower: it is
about the word "complete" and what this codebase currently means by it.

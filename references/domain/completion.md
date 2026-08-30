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

The editorial tag vocabulary in `tag_store.py` covers the first three steps and stops:

| Francisco's step | Tag status |
|---|---|
| script says fully shot | `finished_shooting`, `covered_per_script` |
| assistant mounted it | `ready_to_edit`, `mounted` |
| editor finished editing | `finished` |
| **picture lock** | not represented |
| **sent to colour / sound / VFX** | partly: `needs` carries `sfx`, as a need rather than a stage |
| **conforming** | not represented |
| **DCP** | not represented |

## The problem this exposes

`finished` is described in the code as "No further work expected." Under the chain above that is false: it
names the end of *editorial* as the end of everything, and four stages follow it. A board that says a
scene is finished, when what is meant is that the editor has stopped, tells a colourist something untrue.

Changing the vocabulary is not free -- statuses are stored on tags and mirrored to the trail, so renaming
`finished` or adding stages after it is a migration and a decision, not a rename. Recorded here so the
decision is made deliberately rather than discovered by someone reading a board.

## Related

The delivery chain beyond the cutting room is described in the design workspace at
`references/domain/dept-delivery-chain.md` and `dept-postproduction.md`. This document is narrower: it is
about the word "complete" and what this codebase currently means by it.

---
type: domain
title: What a suffix on a scene number means
description: The tokens production writes beside a scene, and which are confirmed
tags: [domain, scenes, parsing]
status: confirmed
evidence: Francisco, 2026-08-30, answering references/open-questions.md
---

# What a suffix on a scene number means

The daily production report writes scenes as `27pt, 49pt, 117pt, 6WT`. The number is the scene; the
letters are a claim about it.

| Token | Means | Confirmed |
|---|---|---|
| `pt` | **part**: the script notes the scene was not fully shot | yes, Francisco 2026-08-30 |
| `WT` | wild track: sound recorded without picture | yes, long-standing |

## Why `pt` matters more than a label

It is a **third state** in the same family as `Scenes Part Complete`. A scene marked `27pt` on the
scheduled list was never planned to be finished that day, so a later check that treats it as "scheduled,
therefore expected complete" would report a gap the production never intended.

Nothing in the code depends on the meaning yet: the parser extracts the number so a scene can be joined
and keeps the token verbatim. That was the right call while it was unconfirmed, and it stays the right
call now -- the raw token is what the report said, and the meaning is recorded here rather than encoded
in a boolean somebody has to trust.

## The rule this suggests

A suffix is a claim about the scene, not part of its identity. Join on the number; keep the token; look up
what it means here. Guessing produced nothing bad this time only because the parser refused to guess.

---
type: index
title: References
description: What has been learned about this codebase, and what it constrains
tags: [index]
---

# References

What working on CineSpine has taught, kept where the next person can find it.

This tree follows the same two specifications as the design workspace at
`E:\projects\agentic-cinema-design`: **OKF** shapes these documents (markdown, YAML frontmatter, one
required field, reserved `index.md` and `log.md`, broken links legal), and **ICM** shapes the folders.
`_core/CONVENTIONS.md` in that workspace is the source of truth for both.

The division of labour between the two repositories:

| | |
|---|---|
| `agentic-cinema-design` | decides **what must be true**. Requirements, model, contracts. |
| this tree | records **what is true here**, and what that cost to find out. |

A requirement lives there. A defect, a benchmark, or a decision about this build lives here.

## Where things are

| Folder | Question it answers |
|---|---|
| [architecture/](architecture/index.md) | How is this built, and why that way |
| [constraints/](constraints/index.md) | What must not happen, and what shape mistakes take |
| [findings/](findings/index.md) | What was wrong, with the evidence that showed it |
| [domain/](domain/index.md) | What the production world requires of the code |
| [open-questions.md](open-questions.md) | What is not known, written down rather than guessed |

[log.md](log.md) is the chronology: what was learned, when, and from what.

## How to read it

Every claim here should name the thing that produced it -- a measurement, a query, a document, a defect.
A statement with no evidence is a preference, and preferences do not belong in this tree.

Links are untyped and broken links are legal. A link to a document nobody has written yet marks knowledge
that is missing, which is itself information.

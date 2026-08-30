---
type: index
title: Architecture
description: How CineSpine is built, and the reasoning that is easy to lose
tags: [index, architecture]
---

# Architecture

Not a tour of the code -- `AGENTS.md` and `docs/ARCHITECTURE.md` do that. These are the decisions whose
reasoning would otherwise have to be rediscovered, each with the measurement or defect behind it.

| Document | What it settles |
|---|---|
| [persistence.md](persistence.md) | Which store owns what, and why per-event durability was affordable |
| [analytical-mirror.md](analytical-mirror.md) | Why ClickHouse is a mirror and not the source of truth |
| [ingestion-path.md](ingestion-path.md) | How a document becomes events, and where that path can go quiet |

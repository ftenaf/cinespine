---
type: constraints
title: The shapes this repository actually produces
description: Named failure modes with the instance that proved each one, so a review can ask by name
tags: [constraints, quality, review]
status: confirmed
evidence: each entry names its instance
---

# The shapes this repository actually produces

The design workspace catalogues these in general. What follows is the subset **this codebase has
demonstrably produced**, each with the instance. A review can ask for them by name rather than hoping to
notice.

## The confident nothing

A path returns nothing and reports success.

*Instance:* `production.raw.office` had no subscriber. A daily production report ingested to zero events
and answered `INGESTED`, with no dead-letter entry, because no parser ran to fail.

**Check:** can this path return nothing and still report success? A topic with no subscriber, a handler
with no rejection, a query with a filter that matches nothing.

## Absence rendered as presence, and its inverse

*Instance:* two Grafana gauges are declared and never set, so a metric that can never fill looks exactly
like a production with nothing happening. Still open.

*Inverse instance:* the offload gate suppresses the discrepancy entirely, so a day nobody has offloaded
looks like a clean day rather than an unanswered one. Still open.

**Check:** for every empty state, can the reader tell "not here" from "not told yet"?

## The helpful correction

A silent repair that destroys the original.

*Instance:* the PII scrubber turned `A120 280726` into `A[REDACTED_PHONE]`.

**Check:** does this correct, or does it record and leave both values intact?

## Documented, not enforced

A rule stated in a comment that nothing checks.

*Instance:* "self-hosted only" was written in three places and `POSTHOG_HOST=us.i.posthog.com` would have
been accepted. The client-side property filter was a TypeScript type, which stops nothing at runtime.

**Check:** is this rule executed anywhere, or only written down?

## Verification against the wrong instance

*Instances:* twice a console error was blamed on new code when the browser was running a module from
between two edits; once a fix was verified against a `uvicorn` that had not been restarted.

**Check:** restart, then verify. Drop a sentinel into the console and confirm nothing new follows it.

## Fixing the shape, not the case

*Instance:* the shoot-day mistake, three times in three places. See
[domain/shoot-days.md](../domain/shoot-days.md).

**Check:** having fixed this, where else does the same assumption live?

## A correct-looking query over a domain that disagrees

*Instance:* "more than one camera roll for this take" looks like a disagreement scan and reports every
multi-camera setup on the show as a conflict, because a take shot on three cameras carries three rolls and
agrees with itself perfectly.

**Check:** does this aggregate distinguish disagreement from legitimate multiplicity?

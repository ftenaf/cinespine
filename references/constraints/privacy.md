---
type: constraints
title: What may be served
description: Why source documents are gated rather than scrubbed, and what telemetry may carry
tags: [constraints, privacy, safety]
status: confirmed
evidence: shipped scrubber destroyed 'A120 280726'; document endpoints ungated until 2026-08-30
---

# What may be served

A parsed fact is a slate, a roll, a timecode. A **source document** is the page those were read off, and
it carries what the parsers were written to leave behind: a script supervisor's phone number and email in
the footer, crew and cast names, locations, unreleased plot.

Serving the file serves all of it.

## Gate, do not scrub

The instinct is to redact and serve anyway. On production paperwork that destroys data, and this
repository shipped the proof. The scrubber that was here matched a phone-shaped run of digits:

    'A120 280726 2:46'     ->  'A[REDACTED_PHONE] 2:46'
    'Sound Cards: 280726'  ->  'Sound Cards: [REDACTED_PHONE]'

A camera card and its shoot date read as a phone number. Production paperwork is **made of** number
strings that look like phone numbers -- rolls, cards, dates, timecodes, checksums, slate ranges -- so no
broad pattern can be safe here.

So the control is the gate. `CINESPINE_SERVE_SOURCE_DOCUMENTS` is off unless somebody deployed this having
decided otherwise. Redaction remains as defence in depth and is deliberately narrow: an email, or a number
the document itself labels as a phone. Never a bare run of digits.

The embedded demo fixtures are marked synthetic **where they are stored** and served regardless. Seeding
from a local examples directory reads real paperwork, so "it came from the seed endpoint" answers the
wrong question.

## Run the refusal

A gate that has never been executed is not a gate. Every refusal here has a test that exercises it,
including through the bypass that used to exist: `get_document_raw` fell back to reading
`CINESPINE_EXAMPLES_DIR/<filename>`, which reached the real paperwork by name and would have walked
straight around any check on the stored bytes.

## Telemetry

Product analytics go to a **self-hosted** PostHog or nowhere. A host on `posthog.com` is refused, matched
on the domain rather than a list of endpoints so a region added tomorrow is refused without anyone
updating a list.

Autocapture and session replay are off. Autocapture records the text of everything clicked; session replay
records the screen, and the screen is the footage. `/decide` is refused outright, because that is how
capture can be switched on from the server.

Events carry ids and enumerations. Titles, descriptions, notes, filenames and target labels are stripped
centrally on **both** ends -- a TypeScript type stops nothing once a value arrives as `any` -- and
anything over 64 characters is dropped, because a blocklist cannot anticipate every name prose might
arrive under.

## The assumption that is not yet guaranteed

"Parsed facts carry no contact details" is the premise the gate rests on, and nothing enforces it. A
camera CSV row that was not a take at all left a contact line in a `slate` field. See
[open-questions.md](../open-questions.md).

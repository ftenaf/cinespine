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

Product analytics go to PostHog -- self-hosted or their cloud. `POSTHOG_HOST` says which, and it is
required rather than defaulted, so the destination is always something somebody wrote down.

**This changed on 2026-08-30.** The clients used to refuse a host on `posthog.com` outright, on the
argument that shipping this product's telemetry to a third party is a bigger disclosure than the
raw-document endpoint the gate below exists to guard. That check was removed because the deployment may
use PostHog's cloud. The argument was not wrong; the decision is that the disclosure is acceptable, and
what makes it acceptable is that the payload is bounded. So it is worth being exact about the bound.

**What leaves:** which production, which shoot day, which department, which document type, which axis,
which surface was opened, a requirement's status/priority/category, and a role token like
`@sound_supervisor` for who did it.

**What does not:** any text a person typed, any filename, any content, any screenshot. Titles,
descriptions, notes and resolution notes are stripped by name; anything over 64 characters is dropped
whatever it is called, on the reasoning that ids and enumerations are short and prose is not; objects and
arrays are dropped rather than stringified, because stringifying a payload is how content leaks as one
long value. The filter is central, not per call site, because the next call site will be written by
somebody who has not read the file.

Autocapture and session replay are off. Autocapture records the text of everything clicked; session replay
records the screen, and the screen is the footage. Pageviews are off too, because a URL carries the
production id. `/decide` is refused outright, because that is how capture can be switched on from the
server -- which matters more now than it did, not less: with a third-party destination it is the
difference between settings that are ours and settings that can be changed remotely.

`docker-compose.posthog.yml` stands up a self-hosted instance for deployments that would rather none of
this left the machine.

Events carry ids and enumerations. Titles, descriptions, notes, filenames and target labels are stripped
centrally on **both** ends -- a TypeScript type stops nothing once a value arrives as `any` -- and
anything over 64 characters is dropped, because a blocklist cannot anticipate every name prose might
arrive under.

## The premise the gate rests on

"Parsed facts carry no contact details" is what makes it safe to serve them, and until 2026-08-30 nothing
enforced it: a camera CSV row that was not a take at all left a contact line in a `slate` field, which
reached the spine, the analytical mirror and an analytics result.

`parse_camera_csv` now tests the shape of a slate before accepting a row, so a footer or a contact block
cannot become a scene. The test is the shape of a slate rather than a list of junk to exclude, because a
blocklist is the failure mode this project calls the keyed list that rots.

The other parsers have not had the same pass. A row that is not a take is a shape every tabular parser
here can meet.

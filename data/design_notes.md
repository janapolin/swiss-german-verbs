# design_notes.md — UX reference (from the Spanish app screenshots)

These describe the reference app's look and flow. Mirror the structure; adapt content from Spanish
to Swiss German. Dark theme throughout.

## Practice screen (the core flashcard loop)
- Top: thin **progress bar** + label `Daily goal   1 / 50`.
- Large **English prompt** (the verb gloss) near the top, e.g. `to advance`.
- A rounded **card** below containing:
  - a small **tense pill**, colour-coded (green `Future` in the shot),
  - the **pronoun** centered (`él`), with a horizontal rule beneath it (the blank),
  - hint text `Tap to show answer`.
- **On reveal:**
  - the source-language infinitive appears **above** the English gloss
    (ref: `avanzar` over `to advance`) — for us that's the **Swiss German infinitive
    above the English**,
  - the conjugated **answer** appears under the pronoun on the card
    (`él` / `avanzará`) — for us `er` / `er het gmacht`,
  - the hint is replaced by **grade buttons**: a red **thumbs-down** (left half) and a
    green **thumbs-up** (right half), each filling half the card's bottom edge.
- Below the card: three round icon buttons — **history** (clock), **dictionary**
  (book), **audio** (speaker).
- Bottom tab bar: **Practice** (cat icon, active/orange), **Rhymes**, **Verbs**,
  **Settings**.

> NOTE: the reference uses **two** grade buttons (good / hard). Keep the colored split-button visual.

## Verb detail screen (the "Verbs" tab)
- Header: back arrow, verb infinitive, audio icon.
- Flag + English gloss (`to advance`), then a `View all tenses >` row.
- A **tense section** (e.g. `Future`) listing the full conjugation, one row per
  person, each expandable: `yo / tú / él/ella/Ud. / nosotros / ellos…` with the form
  right-aligned. For us: `ich / du / er / mir/ihr/sii` (4 rows, plural collapsed).
- An **"About this tense"** prose blurb explaining usage.
- An additional "edit" option pencil in the top right, which allows editing of all the properties of the verb within the app.

> This confirms two future features worth leaving seams for: a per-verb reference view
> with full tables, and short per-tense explanatory notes. Not required for v1, but the
> data model already supports the tables; the notes would be a new optional field.

## Other tabs
- **Settings** exist in the reference but weren't captured in detail.
  Treat as out of scope for v1 beyond a Settings screen for the profile picker and the
  daily new-card limit.

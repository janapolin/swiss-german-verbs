# Running the Züritüütsch Verb Trainer locally

## 1. One-time setup

```bash
cd swiss-german
python -m venv .venv && source .venv/bin/activate   # if you don't already have .venv
pip install -e ".[dev]"                              # app deps + pytest/ruff/mypy

# Build the database schema and load the seed verbs:
python -m alembic upgrade head
python -m ingestion.ingest
```

`ingest.py` is idempotent — re-run it any time after editing the seed CSVs and it
will upsert in place (146 verbs: 26 irregular + 120 regular).

## 2. Start the app

```bash
uvicorn app.api.main:app --reload
```

Open **http://127.0.0.1:8000** in your browser. First run redirects you to a
profile picker — type a name and hit "Create" (this is just a local label stored
in a cookie + the `profiles` table; no login).

## 3. Using it

- **Practice tab** — the core flashcard loop. Tap the card to reveal the answer
  (Swiss German infinitive + conjugated form), then grade yourself **Hard** (red)
  or **Easy** (green). The scheduler (SM‑2) uses that to decide when you'll see
  the card again — "Hard" brings it back tomorrow, "Easy" pushes the interval out
  further each time you get it right. There's no daily cap on new cards — you'll
  be shown **due reviews first**, then new cards in random order, until every
  enabled verb/tense slot you haven't seen has been introduced. The progress bar
  at the top tracks how many cards you've graded today against a daily goal of 50
  (it keeps counting past 100% — a banner congratulates you on reaching it, but
  there's nothing stopping you from continuing).
- **Verbs tab** — browse all verbs with full conjugation reference tables
  (present / past / future, plus "would" for verbs that have a Konjunktiv II
  form), each row showing a 0–3 star mastery rating per slot derived from your
  review history. Filter tabs (`All` / `Enabled` / `Disabled`) and "Enable All" /
  "Disable All" buttons control which verbs you get drilled on — toggle
  individual verbs with the switch on each row; only enabled verbs show up in
  practice. New profiles start with the top 20 most-frequent verbs enabled. Tap
  the **+** button to add a new verb (infinitive, English meaning, separable
  prefix, auxiliary, all conjugated forms, optional Konjunktiv II, free-text
  notes), or the "Edit" link on a verb's detail page to change one you (or the
  seed data) already added.
- **Settings tab** — toggle which **tenses** (Present / Past / Future / Would)
  get drilled for the active profile, and manage the profile itself: rename it,
  view stats (total reviews, reviews today, distinct cards seen, member-since
  date), switch to a different profile, or delete it (two-step confirmation —
  this also wipes that profile's review history and verb-enablement settings).

## 4. Web / GitHub Pages version

The `docs/` folder is a self-contained static site served by GitHub Pages.
No Python is needed to run it — verb data is pre-rendered to `docs/data/verbs.json`
and user progress is stored in the **browser's own localStorage** (not on any server).

### Running locally

```bash
cd docs
python -m http.server 8080
```

Open **http://localhost:8080**. You must use a local HTTP server (not `file://`) because
ES modules are blocked on `file://` in most browsers.

### Deployed on GitHub Pages

Once the repo has Pages enabled (Settings → Pages → Source: `main`, `/docs`):

- Open **`https://janapolin.github.io/swiss-german-verbs/`** (or whatever the repo name is)
- Create a profile and start practising — progress is saved to that browser's localStorage
- Progress is **device-local**: it does not sync between your laptop and phone

> **Privacy note:** The repo can be private, but the deployed Pages URL is publicly
> accessible to anyone who has it. For personal use this is fine.

### Updating verb data

After editing seed CSVs and re-ingesting:

```bash
source .venv/bin/activate
python -m ingestion.ingest           # rebuild app.db
python -m ingestion.export_json      # regenerate docs/data/verbs.json
git add docs/data/verbs.json && git commit -m "update verb data"
git push                             # GitHub Pages redeploys automatically (~1 min)
```

### Resetting progress (web version)

Browser DevTools → Application → Local Storage → delete all keys starting with `swissverb:`.
Or use the **Delete profile** button in the app's Settings screen.

---

## 5. Re-running tests

```bash
python -m pytest          # 50 tests: rendering, scheduler, ingestion, services, repositories
python -m ruff check .    # lint
```

## 6. Configuration (env vars, all optional)

| Variable | Default | Purpose |
|---|---|---|
| `SWISSVERB_DB_PATH` | `data/app.db` | Where the SQLite file lives |
| `SWISSVERB_AUX_PRESENT_ONLY` | `true` | Limit `haa`/`sii`/`wèèrde` to present-tense cards only |
| `SWISSVERB_DAILY_GOAL_TARGET` | `50` | Target shown in "Daily goal N / target" |
| `SWISSVERB_DEFAULT_ENABLED_VERB_COUNT` | `20` | How many top-frequency verbs a new profile starts with enabled |

## 7. Resetting your progress (Python/local server version)

Your SRS progress (`profiles`, `review_state`, `review_log`, `verb_enablement`)
lives in `data/app.db`, separate from the rebuildable verb content. To start over:

```bash
rm data/app.db
python -m alembic upgrade head
python -m ingestion.ingest
```

> **Caveat:** if you've added or edited verbs through the Verbs tab, **don't**
> do this — those verbs live only in the database, not in the seed CSVs, so
> there's no round-trip back from `ingest`. Resetting the DB will permanently
> lose any verbs you've added or edited (along with all progress). This is a
> known v1 limitation (see CLAUDE.md §11/§13).

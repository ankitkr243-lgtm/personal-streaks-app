# Personal Habit & Reading Tracker

Single-user, self-hosted habit and reading tracker. Markdown files in this
repo are the only source of truth — no database, no cloud hosting.

## Structure

- `/logs/YYYY-MM.md` — one file per month, daily entries as YAML-in-Markdown
- `/library/books.md` — persistent book registry
- `/library/articles.md` — append-only article log
- `config.md` — habit goals and settings
- `/app` — local Flask app (calendar UI, quick-add, library, weekend review)

## Running locally

```
cd app
pip install -r requirements.txt
python app.py
```

Then open `http://localhost:5000`.

The app does a `git pull` before rendering and commits after every save, so
it stays in sync with entries made via other input paths (e.g. mobile).

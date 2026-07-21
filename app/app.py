import calendar as cal_module
from datetime import date, datetime, timedelta

from flask import Flask, render_template, request, redirect, url_for, flash

import markdown_store as store
import compute
import git_sync

app = Flask(__name__)
app.secret_key = "local-only-personal-habit-tracker"


def today():
    return date.today()


@app.before_request
def pull_before_render():
    if request.method == "GET":
        git_sync.pull()


# ---------------------------------------------------------------------------
# Calendar view
# ---------------------------------------------------------------------------

@app.route("/")
def calendar_view():
    t = today()
    year = int(request.args.get("year", t.year))
    month = int(request.args.get("month", t.month))

    config = store.load_config()
    all_logs = store.load_all_logs()
    streaks = compute.compute_streaks(all_logs, config, t)

    cal = cal_module.Calendar(firstweekday=0)  # Monday start
    weeks = []
    for week in cal.monthdatescalendar(year, month):
        row = []
        for d in week:
            ds = d.isoformat()
            entry = all_logs.get(ds)
            in_month = d.month == month
            state = compute.get_day_state(ds, entry, t) if in_month else None
            derived = compute.compute_day_derived(entry["data"], config) if entry else None
            row.append({
                "date": d,
                "in_month": in_month,
                "is_today": d == t,
                "state": state,
                "derived": derived,
                "backfilled": bool(entry["data"].get("backfilled")) if entry else False,
            })
        weeks.append(row)

    prev_month = (date(year, month, 1) - timedelta(days=1))
    next_month = (date(year, month, 28) + timedelta(days=7)).replace(day=1)

    nudge = None
    yesterday_ds = (t - timedelta(days=1)).isoformat()
    if t.isoformat() not in all_logs and yesterday_ds not in all_logs:
        nudge = "Today and yesterday are unlogged."
    elif t.isoformat() not in all_logs:
        nudge = "Today is unlogged."

    return render_template(
        "calendar.html",
        weeks=weeks,
        month_name=cal_module.month_name[month],
        year=year,
        month=month,
        prev_month=prev_month,
        next_month=next_month,
        streaks=streaks,
        nudge=nudge,
        config=config,
    )


# ---------------------------------------------------------------------------
# Quick-add
# ---------------------------------------------------------------------------

@app.route("/quick-add", methods=["GET", "POST"])
def quick_add():
    t = today()
    ds = t.isoformat()

    if request.method == "POST":
        entry = store.load_month_log(t.year, t.month).get(ds, {"data": {}, "notes": ""})
        data = entry["data"]
        notes = entry["notes"]

        steps = request.form.get("steps", "").strip()
        if steps:
            data["steps"] = int(steps)

        book_id = request.form.get("book_id", "").strip()
        pages = request.form.get("pages", "").strip()
        if book_id and pages:
            data.setdefault("reading", [])
            data["reading"].append({"book_id": book_id, "pages": int(pages)})

        article_title = request.form.get("article_title", "").strip()
        if article_title:
            article_source = request.form.get("article_source", "").strip()
            tags = [t.strip() for t in request.form.get("article_tags", "").split(",") if t.strip()]
            article = {"title": article_title, "source": article_source, "tags": tags}
            data.setdefault("professional_reading", [])
            data["professional_reading"].append(article)
            store.append_article({"date": ds, **article})

        new_notes = request.form.get("notes", "").strip()
        if new_notes:
            notes = (notes + "\n\n" + new_notes).strip() if notes else new_notes

        data["state"] = data.get("state", "logged")
        if "backfilled" not in data:
            data["backfilled"] = False

        store.save_day_entry(ds, data, notes)
        git_sync.commit_and_push(f"Log entry for {ds}")
        flash("Saved.")
        return redirect(url_for("quick_add"))

    books = store.load_books()
    in_progress_books = {bid: b for bid, b in books.items() if b.get("status") == "in_progress"}
    return render_template("quick_add.html", books=in_progress_books, today=ds)


@app.route("/quick-add/new-book", methods=["POST"])
def new_book():
    title = request.form.get("title", "").strip()
    author = request.form.get("author", "").strip()
    total_pages = request.form.get("total_pages", "").strip()

    books = store.load_books()
    slug = store.next_available_slug(store.slugify(title), set(books.keys()))
    book = {
        "id": slug,
        "title": title,
        "author": author,
        "total_pages": int(total_pages) if total_pages else None,
        "status": "in_progress",
        "start_date": today().isoformat(),
        "finish_date": None,
        "tags": [],
    }
    store.save_book(book)
    git_sync.commit_and_push(f"Add book: {title}")
    flash(f'Added "{title}" to your library.')
    return redirect(url_for("quick_add"))


# ---------------------------------------------------------------------------
# Library
# ---------------------------------------------------------------------------

@app.route("/library")
def library():
    books = store.load_books()
    all_logs = store.load_all_logs()
    page_totals = compute.compute_book_pages(all_logs)

    book_list = []
    for bid, b in books.items():
        current_page = page_totals.get(bid, 0)
        total = b.get("total_pages") or 0
        pct = min(100, round(100 * current_page / total)) if total else 0
        book_list.append({**b, "current_page": current_page, "progress_pct": pct})
    book_list.sort(key=lambda b: (b.get("status") != "in_progress", b.get("title", "")))

    articles = list(reversed(store.load_articles()))
    tag_filter = request.args.get("tag")
    all_tags = sorted({tag for a in articles for tag in (a.get("tags") or [])})
    if tag_filter:
        articles = [a for a in articles if tag_filter in (a.get("tags") or [])]

    return render_template(
        "library.html", books=book_list, articles=articles, all_tags=all_tags, tag_filter=tag_filter
    )


# ---------------------------------------------------------------------------
# Weekend review
# ---------------------------------------------------------------------------

@app.route("/review")
def review():
    t = today()
    config = store.load_config()
    all_logs = store.load_all_logs()

    missed = []
    for i in range(1, 8):
        d = t - timedelta(days=i)
        ds = d.isoformat()
        entry = all_logs.get(ds)
        state = compute.get_day_state(ds, entry, t)
        if state == "missed":
            missed.append({"date": d, "date_str": ds})

    books = store.load_books()
    in_progress_books = {bid: b for bid, b in books.items() if b.get("status") == "in_progress"}
    return render_template("review.html", missed=missed, books=in_progress_books)


@app.route("/review/backfill", methods=["POST"])
def review_backfill():
    ds = request.form.get("date")

    data = {"state": "reviewed", "backfilled": True}
    steps = request.form.get("steps", "").strip()
    if steps:
        data["steps"] = int(steps)

    book_id = request.form.get("book_id", "").strip()
    pages = request.form.get("pages", "").strip()
    if book_id and pages:
        data["reading"] = [{"book_id": book_id, "pages": int(pages)}]

    article_title = request.form.get("article_title", "").strip()
    if article_title:
        article_source = request.form.get("article_source", "").strip()
        tags = [t.strip() for t in request.form.get("article_tags", "").split(",") if t.strip()]
        article = {"title": article_title, "source": article_source, "tags": tags}
        data["professional_reading"] = [article]
        store.append_article({"date": ds, **article})

    notes = request.form.get("notes", "").strip()
    store.save_day_entry(ds, data, notes)
    git_sync.commit_and_push(f"Backfill entry for {ds}")
    flash(f"Backfilled {ds}.")
    return redirect(url_for("review"))


@app.route("/review/mark-reviewed", methods=["POST"])
def review_mark_reviewed():
    ds = request.form.get("date")
    data = {"state": "reviewed", "backfilled": False}
    store.save_day_entry(ds, data, notes="")
    git_sync.commit_and_push(f"Mark {ds} reviewed (no backfill)")
    flash(f"Marked {ds} as reviewed.")
    return redirect(url_for("review"))


if __name__ == "__main__":
    app.run(debug=True, port=5000)

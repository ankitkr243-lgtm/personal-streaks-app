"""Read/write access to the Markdown+YAML files that are this app's only
source of truth (logs, books, articles, config). No data is persisted
anywhere else.
"""
import os
import re
import yaml

HEADING_RE = re.compile(r"^## (.+)$", re.MULTILINE)
YAML_BLOCK_RE = re.compile(r"```yaml\n(.*?)\n```", re.DOTALL)
DAY_HEADING_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}) \((\w+)\)$")


def _repo_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _split_sections(text):
    """Split a Markdown file into (heading, body) sections on top-level `## ` headings."""
    matches = list(HEADING_RE.finditer(text))
    sections = []
    for i, m in enumerate(matches):
        heading = m.group(1)
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end]
        sections.append((heading, body))
    return sections


def _parse_section_body(body):
    """Extract the YAML block and freeform notes text from a section body."""
    m = YAML_BLOCK_RE.search(body)
    data = yaml.safe_load(m.group(1)) if m else {}
    notes = ""
    if m:
        after = body[m.end():]
        notes_m = re.search(r"\*\*Notes:\*\*\n(.*?)(?:\n---\s*$|\Z)", after, re.DOTALL)
        if notes_m:
            notes = notes_m.group(1).strip()
    return data or {}, notes


def _render_section(heading, data, notes=""):
    yaml_text = yaml.safe_dump(data, sort_keys=False, default_flow_style=False).strip()
    out = f"## {heading}\n```yaml\n{yaml_text}\n```\n"
    if notes:
        out += f"\n**Notes:**\n{notes}\n"
    out += "\n---\n\n"
    return out


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def load_config():
    path = os.path.join(_repo_root(), "config.md")
    with open(path) as f:
        text = f.read()
    sections = _split_sections(text)
    for heading, body in sections:
        if heading.strip() == "Config":
            data, _ = _parse_section_body(body)
            return data
    raise ValueError("config.md has no ## Config section")


# ---------------------------------------------------------------------------
# Daily logs
# ---------------------------------------------------------------------------

def _month_log_path(year, month):
    return os.path.join(_repo_root(), "logs", f"{year:04d}-{month:02d}.md")


def load_month_log(year, month):
    """Returns {date_str: {'data': {...}, 'notes': str, 'weekday': str}}"""
    path = _month_log_path(year, month)
    entries = {}
    if not os.path.exists(path):
        return entries
    with open(path) as f:
        text = f.read()
    for heading, body in _split_sections(text):
        m = DAY_HEADING_RE.match(heading.strip())
        if not m:
            continue
        date_str, weekday = m.group(1), m.group(2)
        data, notes = _parse_section_body(body)
        entries[date_str] = {"data": data, "notes": notes, "weekday": weekday}
    return entries


def load_all_logs():
    """Scans every /logs/YYYY-MM.md file. Returns {date_str: {...}} across all months."""
    logs_dir = os.path.join(_repo_root(), "logs")
    all_entries = {}
    if not os.path.isdir(logs_dir):
        return all_entries
    for fname in sorted(os.listdir(logs_dir)):
        m = re.match(r"^(\d{4})-(\d{2})\.md$", fname)
        if not m:
            continue
        year, month = int(m.group(1)), int(m.group(2))
        all_entries.update(load_month_log(year, month))
    return all_entries


def save_day_entry(date_str, data, notes="", weekday=None):
    """Create or overwrite the section for `date_str` in its month file."""
    from datetime import datetime
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    if weekday is None:
        weekday = dt.strftime("%A")
    path = _month_log_path(dt.year, dt.month)

    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not os.path.exists(path):
        header = f"# {dt.year:04d}-{dt.month:02d}\n\nDaily log entries for {dt.strftime('%B %Y')}.\n\n"
        with open(path, "w") as f:
            f.write(header)

    with open(path) as f:
        text = f.read()

    sections = _split_sections(text)
    preamble_end = HEADING_RE.search(text)
    preamble = text[: preamble_end.start()] if preamble_end else text

    heading_label = f"{date_str} ({weekday})"
    new_section = _render_section(heading_label, data, notes)

    rebuilt = []
    inserted = False
    for heading, body in sections:
        m = DAY_HEADING_RE.match(heading.strip())
        if m and m.group(1) == date_str:
            rebuilt.append((heading_label, new_section))
            inserted = True
        elif m and not inserted and m.group(1) > date_str:
            rebuilt.append((heading_label, new_section))
            rebuilt.append((heading, _render_section(heading, *_parse_section_body(body))))
            inserted = True
        else:
            rebuilt.append((heading, _render_section(heading, *_parse_section_body(body))))
    if not inserted:
        rebuilt.append((heading_label, new_section))

    with open(path, "w") as f:
        f.write(preamble)
        for _, rendered in rebuilt:
            f.write(rendered)


# ---------------------------------------------------------------------------
# Books
# ---------------------------------------------------------------------------

def _books_path():
    return os.path.join(_repo_root(), "library", "books.md")


def load_books():
    """Returns {book_id: data_dict}."""
    path = _books_path()
    books = {}
    if not os.path.exists(path):
        return books
    with open(path) as f:
        text = f.read()
    for heading, body in _split_sections(text):
        data, _ = _parse_section_body(body)
        if data and "id" in data:
            books[data["id"]] = data
    return books


def slugify(title):
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug


def next_available_slug(base_slug, existing_ids):
    if base_slug not in existing_ids:
        return base_slug
    i = 2
    while f"{base_slug}-{i}" in existing_ids:
        i += 1
    return f"{base_slug}-{i}"


def save_book(book_data):
    """Create or update a book entry, keyed by book_data['id']."""
    path = _books_path()
    if not os.path.exists(path):
        with open(path, "w") as f:
            f.write("# Books\n\nOne `##` heading per book.\n\n")
    with open(path) as f:
        text = f.read()

    sections = _split_sections(text)
    preamble_end = HEADING_RE.search(text)
    preamble = text[: preamble_end.start()] if preamble_end else text

    target_id = book_data["id"]
    rendered_new = _render_section(book_data["title"], book_data)

    rebuilt = []
    found = False
    for heading, body in sections:
        data, _ = _parse_section_body(body)
        if data.get("id") == target_id:
            rebuilt.append(rendered_new)
            found = True
        else:
            rebuilt.append(_render_section(heading, data))
    if not found:
        rebuilt.append(rendered_new)

    with open(path, "w") as f:
        f.write(preamble)
        for r in rebuilt:
            f.write(r)


# ---------------------------------------------------------------------------
# Articles
# ---------------------------------------------------------------------------

def _articles_path():
    return os.path.join(_repo_root(), "library", "articles.md")


def load_articles():
    path = _articles_path()
    articles = []
    if not os.path.exists(path):
        return articles
    with open(path) as f:
        text = f.read()
    for heading, body in _split_sections(text):
        data, _ = _parse_section_body(body)
        if data:
            articles.append(data)
    return articles


def append_article(article_data):
    path = _articles_path()
    if not os.path.exists(path):
        with open(path, "w") as f:
            f.write("# Articles\n\nAppend-only index of professional reading, most recent last.\n\n")
    heading = f"{article_data['date']} — {article_data['title']}"
    with open(path, "a") as f:
        f.write(_render_section(heading, article_data))

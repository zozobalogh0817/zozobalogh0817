#!/usr/bin/env python3
import os
import sys
import json
import time
import datetime as dt
from urllib import request, parse, error
from typing import Dict, List, Tuple

API = "https://api.github.com"
START_MARK = "<!--START_SECTION:DYNAMIC-->"
END_MARK = "<!--END_SECTION:DYNAMIC-->"


def env_owner_fallback() -> str:
    repo = os.getenv("GITHUB_REPOSITORY", "")  # e.g. owner/repo
    if "/" in repo:
        return repo.split("/", 1)[0]
    owner = os.getenv("GITHUB_REPOSITORY_OWNER")
    if owner:
        return owner
    return os.getenv("GITHUB_ACTOR", "zozobalogh0817")


def gh_headers() -> Dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "readme-updater"
    }
    token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def gh_get(url: str, params: Dict[str, str] | None = None) -> Tuple[int, Dict, Dict[str, List[str]]]:
    if params:
        url = f"{url}?{parse.urlencode(params)}"
    req = request.Request(url, headers=gh_headers())
    try:
        with request.urlopen(req, timeout=30) as resp:
            data = resp.read()
            charset = resp.headers.get_content_charset() or "utf-8"
            text = data.decode(charset)
            return resp.status, json.loads(text), dict(resp.headers)
    except error.HTTPError as e:
        try:
            body = e.read().decode("utf-8", errors="ignore")
            j = json.loads(body) if body else {"message": body}
        except Exception:
            j = {"message": str(e)}
        return e.code, j, dict(getattr(e, 'headers', {}))
    except Exception as e:
        return 0, {"message": str(e)}, {}


def paginate(url: str, base_params: Dict[str, str] | None = None, max_pages: int = 10) -> List[Dict]:
    items: List[Dict] = []
    page = 1
    while page <= max_pages:
        params = dict(base_params or {})
        params.update({"page": page, "per_page": 100})
        code, data, _ = gh_get(url, params)
        if code != 200 or not isinstance(data, list) or not data:
            break
        items.extend(data)
        page += 1
    return items


def get_user(owner: str) -> Dict:
    code, data, _ = gh_get(f"{API}/users/{owner}")
    return data if code == 200 else {}


def get_repos(owner: str) -> List[Dict]:
    # Owner's repositories (not including orgs) sorted by updated
    return paginate(f"{API}/users/{owner}/repos", {"type": "owner", "sort": "updated"})


def get_events(owner: str) -> List[Dict]:
    code, data, _ = gh_get(f"{API}/users/{owner}/events/public", {"per_page": 50})
    return data if code == 200 and isinstance(data, list) else []


def sum_stars(repos: List[Dict]) -> int:
    return sum(int(r.get("stargazers_count", 0) or 0) for r in repos)


def top_languages(repos: List[Dict], owner: str, top_n: int = 5) -> List[Tuple[str, int, float]]:
    totals: Dict[str, int] = {}
    for r in repos:
        # Skip archived or forked to better reflect authored code
        if r.get("fork") or r.get("archived"):
            continue
        lang_url = r.get("languages_url")
        if not lang_url:
            continue
        code, data, _ = gh_get(lang_url)
        if code == 200 and isinstance(data, dict):
            for k, v in data.items():
                totals[k] = totals.get(k, 0) + int(v or 0)
        # Be polite to API
        time.sleep(0.2)
    grand = sum(totals.values()) or 1
    ranked = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)[:top_n]
    return [(name, bytes_, (bytes_ / grand) * 100.0) for name, bytes_ in ranked]


def recent_pushes(repos: List[Dict], top_n: int = 5) -> List[Tuple[str, str, str]]:
    # Return (name, html_url, pushed_at_iso)
    own = [r for r in repos if not r.get("fork")]
    own.sort(key=lambda r: r.get("pushed_at") or r.get("updated_at") or "", reverse=True)
    out = []
    for r in own[:top_n]:
        out.append((r.get("full_name") or r.get("name"), r.get("html_url"), r.get("pushed_at") or r.get("updated_at")))
    return out


def humanize_ago(iso_time: str) -> str:
    try:
        t = dt.datetime.fromisoformat(iso_time.replace("Z", "+00:00"))
        delta = dt.datetime.now(dt.timezone.utc) - t
        secs = int(delta.total_seconds())
        if secs < 60:
            return f"{secs}s ago"
        mins = secs // 60
        if mins < 60:
            return f"{mins}m ago"
        hrs = mins // 60
        if hrs < 48:
            return f"{hrs}h ago"
        days = hrs // 24
        return f"{days}d ago"
    except Exception:
        return iso_time


def format_event_line(ev: Dict) -> str:
    et = ev.get("type")
    repo = ev.get("repo", {}).get("name", "")
    repo_url = f"https://github.com/{repo}" if repo else ""
    created_at = ev.get("created_at", "")
    ago = humanize_ago(created_at) if created_at else ""

    if et == "PushEvent":
        commits = len(ev.get("payload", {}).get("commits", []) or [])
        branch = ev.get("payload", {}).get("ref", "").split("/")[-1]
        return f"- ⬆️ Pushed {commits} commit(s) to `{branch}` in [`{repo}`]({repo_url}) · {ago}"
    if et == "PullRequestEvent":
        action = ev.get("payload", {}).get("action", "")
        pr = ev.get("payload", {}).get("pull_request", {})
        num = pr.get("number") or ev.get("payload", {}).get("number")
        url = pr.get("html_url") or (f"{repo_url}/pull/{num}" if (repo and num) else repo_url)
        return f"- 🔀 {action.capitalize()} PR [#{num}]({url}) in [`{repo}`]({repo_url}) · {ago}"
    if et == "IssuesEvent":
        action = ev.get("payload", {}).get("action", "")
        issue = ev.get("payload", {}).get("issue", {})
        num = issue.get("number")
        url = issue.get("html_url") or (f"{repo_url}/issues/{num}" if (repo and num) else repo_url)
        return f"- 🐛 {action.capitalize()} issue [#{num}]({url}) in [`{repo}`]({repo_url}) · {ago}"
    if et == "IssueCommentEvent":
        action = ev.get("payload", {}).get("action", "")
        url = ev.get("payload", {}).get("comment", {}).get("html_url", repo_url)
        return f"- 💬 {action.capitalize()} a comment in [`{repo}`]({repo_url}) · {ago}"
    if et == "CreateEvent":
        ref_type = ev.get("payload", {}).get("ref_type", "")
        ref = ev.get("payload", {}).get("ref", "")
        return f"- ✨ Created {ref_type} `{ref}` in [`{repo}`]({repo_url}) · {ago}"
    if et == "DeleteEvent":
        ref_type = ev.get("payload", {}).get("ref_type", "")
        ref = ev.get("payload", {}).get("ref", "")
        return f"- 🗑️ Deleted {ref_type} `{ref}` in [`{repo}`]({repo_url}) · {ago}"

    # Fallback generic line
    return f"- 📌 {et} in [`{repo}`]({repo_url}) · {ago}"


def build_dynamic_markdown(owner: str) -> str:
    user = get_user(owner)
    repos = get_repos(owner)

    public_repos = user.get("public_repos", len(repos)) if isinstance(user, dict) else len(repos)
    stars = sum_stars(repos)
    langs = top_languages(repos, owner, top_n=5)
    pushes = recent_pushes(repos, top_n=5)

    events = get_events(owner)
    event_lines: List[str] = []
    for ev in events:
        line = format_event_line(ev)
        if line:
            event_lines.append(line)
        if len(event_lines) >= 5:
            break

    now_utc = dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

    md: List[str] = []
    md.append(f"_Last updated: **{now_utc}**_")
    md.append("")
    md.append("#### GitHub Stats")
    md.append(f"- Public repositories: **{public_repos}**")
    md.append(f"- Total stars (across public repos): **{stars}**")
    md.append("")

    if langs:
        md.append("#### Top Languages (by code size)")
        for name, bytes_, pct in langs:
            md.append(f"- {name}: {pct:.1f}%")
        md.append("")

    if pushes:
        md.append("#### Recently pushed repositories")
        for name, url, pushed in pushes:
            md.append(f"- [`{name}`]({url}) · {humanize_ago(pushed)}")
        md.append("")

    if event_lines:
        md.append("#### Recent public activity")
        md.extend(event_lines)
        md.append("")

    return "\n".join(md).strip() + "\n"


def replace_between_markers(text: str, start: str, end: str, replacement: str) -> str:
    if start in text and end in text and text.index(start) < text.index(end):
        before = text.split(start, 1)[0]
        after = text.split(end, 1)[1]
        return f"{before}{start}\n{replacement}{end}{after}"
    # If markers missing, append at end with markers
    if not text.endswith("\n"):
        text += "\n"
    return text + f"\n{start}\n{replacement}{end}\n"


def main() -> int:
    owner = env_owner_fallback()
    readme_path = os.path.join(os.getcwd(), "README.md")
    if not os.path.exists(readme_path):
        print("README.md not found", file=sys.stderr)
        return 2

    dynamic_md = build_dynamic_markdown(owner)
    with open(readme_path, "r", encoding="utf-8") as f:
        original = f.read()

    updated = replace_between_markers(original, START_MARK, END_MARK, dynamic_md)

    if updated != original:
        with open(readme_path, "w", encoding="utf-8") as f:
            f.write(updated)
        print("README.md updated")
    else:
        print("No changes to README.md")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

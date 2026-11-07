#!usr/bin/env python3
"""Refresh ManyaJain111's profile README with a Pokedex-style status card."""
 
import argparse
import json
import os
import textwrap
from collections import Counter
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path
from urllib.request import Request, urlopen
 
 
USERNAME = "ManyaJain111"
TOKEN = os.environ.get("GH_PAT", "")
CITY = "Hyderabad"
 
README = "README.md"
ASSETS = Path("assets")
 
IST = timezone(timedelta(hours=5, minutes=30))
 
# Muted pink palette with Pikachu-yellow accents
PINK = "#d4919c"
DARK_PINK = "#9e5a67"
ROSE = "#b0475b"
YELLOW = "#ffcb05"
INK = "#1b1b1f"
LCD = "#9bc79b"
LCD_INK = "#1e3a1e"
 
 
# ---------- GitHub API ----------
 
def github_get(url):
    req = Request(
        url,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urlopen(req, timeout=20) as response:
        return json.loads(response.read())
 
 
def github_graphql(query, variables):
    payload = json.dumps({"query": query, "variables": variables}).encode()
    req = Request(
        "https://api.github.com/graphql",
        data=payload,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
        },
    )
    with urlopen(req, timeout=20) as response:
        result = json.loads(response.read())
 
    if "errors" in result:
        raise RuntimeError(result["errors"])
    return result["data"]
 
 
# ---------- Status and weather ----------
 
def get_status(hour):
    """Pokemon-flavoured status for the hour of day (IST)."""
    if hour < 2:
        return "Gengar hours: coding in the dark"
    if hour < 6:
        return "Snorlax is blocking the path"
    if hour < 9:
        return "Training at the gym for the next badge"
    if hour < 12:
        return "Pikachu used Thunderbolt on the backlog"
    if hour < 15:
        return "Healing up at the Pokémon Center"
    if hour < 20:
        return "A wild bug appeared!"
    return "Using Quick Attack on a deadline"
 
 
def get_weather():
    try:
        req = Request(
            f"https://wttr.in/{CITY}?format=j1",
            headers={"User-Agent": "README-refresh/1.0"},
        )
        with urlopen(req, timeout=15) as response:
            now = json.loads(response.read())["current_condition"][0]
 
        return {
            "location": CITY,
            "temperature": f"{now['temp_C']}°C",
            "condition": now["weatherDesc"][0]["value"],
        }
    except Exception:
        return {"location": CITY, "temperature": None, "condition": "unavailable"}
 
 
# ---------- Repos and activity ----------
 
def is_profile_repo(name):
    """True for the ManyaJain111/ManyaJain111 profile repo."""
    return name.split("/")[-1].lower() == USERNAME.lower()
 
 
def get_repositories():
    repos = []
    page = 1
 
    while True:
        data = github_get(
            f"https://api.github.com/users/{USERNAME}/repos"
            f"?per_page=100&page={page}&type=owner&sort=pushed"
        )
        repos.extend(data)
        if len(data) < 100:
            break
        page += 1
 
    return [r for r in repos if not r["fork"] and not r["archived"]]
 
 
def get_languages(repos):
    totals = Counter()
 
    for repo in repos:
        try:
            for lang, size in github_get(repo["languages_url"]).items():
                totals[lang] += size
        except Exception as e:
            print(f"Could not read languages for {repo['name']}: {e}")
 
    return [lang for lang, _ in totals.most_common(5)]
 
 
def get_latest_push(repos):
    """Most recent public push by the user, skipping the profile repo.
 
    Uses the user's own push events, so README refreshes by the Actions
    bot never count. Falls back to the most recently pushed repo.
    """
    try:
        events = github_get(
            f"https://api.github.com/users/{USERNAME}/events/public?per_page=100"
        )
        for event in events:
            full = event["repo"]["name"]
            if event.get("type") != "PushEvent" or is_profile_repo(full):
                continue
 
            date = event["created_at"]
            message = None
            try:
                commit = github_get(
                    f"https://api.github.com/repos/{full}/commits/{event['payload']['head']}"
                )["commit"]
                message = commit["message"].strip().splitlines()[0]
                date = commit["author"]["date"]
            except Exception as e:
                print(f"Could not read head commit of {full}: {e}")
 
            return full.split("/", 1)[-1], date, message
    except Exception as e:
        print(f"Could not read push events: {e}")
 
    others = [r for r in repos if not is_profile_repo(r["name"])]
    if not others:
        return None, None, None
    latest = max(others, key=lambda r: r.get("pushed_at") or "")
    return latest["name"], latest.get("pushed_at"), None
 
 
def get_repo_stats(repos):
    """Total repo count, total stars, and the most-starred repo."""
    stars = sum(r.get("stargazers_count", 0) for r in repos)
 
    best = None
    if repos:
        top = max(repos, key=lambda r: r.get("stargazers_count", 0))
        if top.get("stargazers_count", 0) > 0:
            best = {"name": top["name"], "stars": top["stargazers_count"]}
 
    return {"total_repos": len(repos), "total_stars": stars, "most_starred_repo": best}
 
 
def get_activity():
    """Commits in the last 7 days, plus open issues and PRs authored by the user."""
    since = (datetime.now(timezone.utc) - timedelta(days=7)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    query = """
    query($login: String!, $since: DateTime!) {
      user(login: $login) {
        contributionsCollection(from: $since) { totalCommitContributions }
        issues(states: OPEN) { totalCount }
        pullRequests(states: OPEN) { totalCount }
      }
    }
    """
    user = github_graphql(query, {"login": USERNAME, "since": since})["user"]
    return (
        user["contributionsCollection"]["totalCommitContributions"],
        user["issues"]["totalCount"],
        user["pullRequests"]["totalCount"],
    )
 
 
def get_contribution_stats():
    """Current and longest daily contribution streaks over the last year."""
    query = """
    query($login: String!) {
      user(login: $login) {
        contributionsCollection {
          contributionCalendar {
            weeks { contributionDays { date contributionCount } }
          }
        }
      }
    }
    """
    weeks = github_graphql(query, {"login": USERNAME})["user"][
        "contributionsCollection"
    ]["contributionCalendar"]["weeks"]
 
    days = sorted(
        (d for w in weeks for d in w["contributionDays"]), key=lambda d: d["date"]
    )
    counts = [d["contributionCount"] for d in days]
 
    longest = streak = 0
    for count in counts:
        streak = streak + 1 if count > 0 else 0
        longest = max(longest, streak)
 
    current = 0
    for count in reversed(counts):
        if count == 0:
            break
        current += 1
 
    return current, longest
 
 
# ---------- Rendering ----------
 
def ago(iso):
    if not iso:
        return "unknown"
    delta = datetime.now(timezone.utc) - datetime.fromisoformat(
        iso.replace("Z", "+00:00")
    )
    minutes = int(delta.total_seconds() // 60)
    for unit, size in (("d", 1440), ("h", 60)):
        if minutes >= size:
            return f"{minutes // size}{unit} ago"
    return f"{max(minutes, 0)}m ago"
 
 
def fmt(value, suffix=""):
    return "n/a" if value is None else f"{value}{suffix}"
 
 
def clip(text, width):
    return text if len(text) <= width else text[: width - 1] + "…"
 
 
def wrap(text, width, rows):
    """Wrap text into at most `rows` lines, ending with an ellipsis if cut."""
    lines = textwrap.wrap(text, width=width) or [""]
    if len(lines) > rows:
        lines = lines[:rows]
        lines[-1] = lines[-1].rstrip(".,;: ")[: width - 1] + "…"
    return lines
 
 
def render_header():
    """Lens, indicator lights, title and the stepped top edge."""
    return f"""
<circle cx="78" cy="62" r="40" fill="#fff" stroke="{INK}" stroke-width="3"/>
<circle cx="78" cy="62" r="30" fill="#2a9fe0" stroke="{INK}" stroke-width="2"/>
<circle cx="68" cy="51" r="9" fill="#fff" opacity=".75"/>
<circle cx="150" cy="34" r="9" fill="#ff4d4d" stroke="{INK}" stroke-width="2"/>
<circle cx="178" cy="34" r="9" fill="{YELLOW}" stroke="{INK}" stroke-width="2"/>
<circle cx="206" cy="34" r="9" fill="#4cd964" stroke="{INK}" stroke-width="2"/>
<text x="140" y="86" class="title">TRAINER DEX</text>
<text x="352" y="86" class="handle">@{escape(USERNAME.upper())}</text>
<path d="M0 118 H560 L600 146 H960" fill="none" stroke="{INK}" stroke-width="3"/>
<path d="M906 22 L876 66 H896 L884 104 L922 52 H900 L914 22 Z" fill="{YELLOW}" stroke="{INK}" stroke-width="2.5" stroke-linejoin="round"/>
    """
 
 
def render_screen(data):
    """Left LCD screen: status, weather, latest push."""
    gh, wx = data["github"], data["weather"]
 
    status = "".join(
        f'<text x="88" y="{256 + n * 34}" class="status">{escape(line)}</text>'
        for n, line in enumerate(wrap(data["status"], 26, 2))
    )
    habitat = (
        f"{wx['location']} · {wx['temperature']} · {wx['condition']}"
        if wx["temperature"]
        else f"{wx['location']} · weather unavailable"
    )
    repo = escape(clip(gh["latest_active_repo"] or "n/a", 32))
    message = gh.get("last_commit_message") or "no commit message"
    msg = "".join(
        f'<text x="88" y="{424 + n * 19}" class="msg">{escape(line)}</text>'
        for n, line in enumerate(wrap(f"“{message}”", 50, 2))
    )
 
    return f"""
<rect x="40" y="166" width="520" height="350" rx="16" fill="#dedede" stroke="{INK}" stroke-width="3"/>
<circle cx="276" cy="180" r="4" fill="{ROSE}"/><circle cx="298" cy="180" r="4" fill="{ROSE}"/>
<rect x="64" y="192" width="472" height="278" rx="8" fill="{LCD}" stroke="{INK}" stroke-width="2"/>
<text x="88" y="216" class="lcd-k">RIGHT NOW</text>
{status}
<text x="88" y="334" class="lcd">HABITAT  {escape(habitat)}</text>
<line x1="88" y1="350" x2="512" y2="350" stroke="{LCD_INK}" stroke-width="1" stroke-dasharray="4 4" opacity=".5"/>
<text x="88" y="374" class="lcd-k">LAST SEEN  ·  {escape(ago(gh["last_commit"]).upper())}</text>
<text x="88" y="402" class="repo">{repo}</text>
{msg}
<circle cx="84" cy="494" r="10" fill="{ROSE}" stroke="{INK}" stroke-width="2"/>
<g stroke="{INK}" stroke-width="3" stroke-linecap="round">
  <line x1="470" y1="488" x2="530" y2="488"/><line x1="470" y1="497" x2="530" y2="497"/><line x1="470" y1="506" x2="530" y2="506"/>
</g>
"""
 
 
def render_stats(gh):
    """Right panel: base-stat bars, each scaled against a cap."""
    stats = [
        ("REPOS", gh["total_repos"], 50, ""),
        ("STARS", gh["total_stars"], 50, ""),
        ("COMMITS / WEEK", gh.get("commits_last_7_days"), 40, ""),
        ("OPEN ISSUES", gh.get("open_issues"), 10, ""),
        ("OPEN PRS", gh.get("open_prs"), 10, ""),
        ("BEST STREAK", gh.get("longest_streak"), 30, " d"),
    ]
 
    rows = ""
    for i, (label, value, cap, suffix) in enumerate(stats):
        y = 224 + i * 50
        fill = 0 if value is None else 290 * min(value / cap, 1)
        rows += (
            f'<text x="610" y="{y}" class="stat-k">{label}</text>'
            f'<text x="900" y="{y}" class="stat-v" text-anchor="end">{escape(fmt(value, suffix))}</text>'
            f'<rect x="610" y="{y + 9}" width="290" height="9" rx="4.5" fill="#3a3a44"/>'
            f'<rect x="610" y="{y + 9}" width="{fill:.0f}" height="9" rx="4.5" fill="{YELLOW}"/>'
        )
 
    return f"""
<rect x="590" y="166" width="330" height="350" rx="12" fill="#1d1d23" stroke="{INK}" stroke-width="3"/>
<text x="610" y="194" class="lcd-k" style="fill:{YELLOW}">BASE STATS</text>
{rows}
"""
 
 
def render_footer(data):
    """Bottom strip: top languages as move chips, plus the update time."""
    chips = ""
    x = 124
    for lang in data["github"]["top_languages"][:5]:
        width = len(lang) * 8 + 26
        if x + width > 680:
            break
        chips += (
            f'<rect x="{x}" y="538" width="{width}" height="26" rx="13" fill="{YELLOW}" stroke="{INK}" stroke-width="2"/>'
            f'<text x="{x + width / 2:.0f}" y="556" class="chip" text-anchor="middle">{escape(lang)}</text>'
        )
        x += width + 10
 
    return f"""
<text x="40" y="556" class="foot-k">MOVES</text>
{chips or '<text x="124" y="556" class="foot">n/a</text>'}
<text x="920" y="556" class="foot" text-anchor="end">updated {escape(data["updated"])}</text>
"""
 
 
def render_svg(data):
    mono = "ui-monospace, 'SF Mono', Menlo, Consolas, monospace"
    sans = "'Trebuchet MS', Verdana, 'Segoe UI', sans-serif"
 
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="960" height="600" viewBox="0 0 960 600" role="img" aria-label="Live status for {USERNAME}: {escape(data["status"])}">
<style>
.title {{ font: 800 26px {sans}; fill:#fff; letter-spacing: 2px; }}
.handle {{ font: 700 16px {mono}; fill:{INK}; letter-spacing: 1px; }}
.lcd-k {{ font: 700 11px {mono}; fill:{LCD_INK}; letter-spacing: .18em; }}
.lcd {{ font: 13px {mono}; fill:{LCD_INK}; }}
.status {{ font: 800 27px {sans}; fill:{LCD_INK}; }}
.repo {{ font: 700 21px {sans}; fill:{LCD_INK}; }}
.msg {{ font: italic 14px {mono}; fill:{LCD_INK}; opacity:.85; }}
.stat-k {{ font: 700 11px {mono}; fill:#d8d8de; letter-spacing: .14em; }}
.stat-v {{ font: 700 18px {mono}; fill:#fff; }}
.chip {{ font: 700 13px {mono}; fill:{INK}; }}
.foot-k {{ font: 800 14px {sans}; fill:#fff; letter-spacing: 2px; }}
.foot {{ font: 12px {mono}; fill:#fff; }}
</style>
<rect x="2" y="2" width="956" height="596" rx="28" fill="{PINK}" stroke="{DARK_PINK}" stroke-width="4"/>
{render_header()}
{render_screen(data)}
{render_stats(data["github"])}
{render_footer(data)}
</svg>
"""
 
 
SAMPLE = {
    "status": get_status(10),
    "weather": {"location": CITY, "temperature": "29°C", "condition": "Partly cloudy"},
    "github": {
        "top_languages": ["Python", "Jupyter Notebook", "C++", "JavaScript"],
        "latest_active_repo": "sae-gated-rag-experiments",
        "last_commit": "2026-11-07T04:12:00Z",
        "last_commit_message": "eval: add retrieval gating ablation and fix seed handling",
        "current_streak": 4,
        "commits_last_7_days": 18,
        "open_issues": 2,
        "open_prs": 1,
        "longest_streak": 15,
        "total_repos": 23,
        "total_stars": 11,
        "most_starred_repo": {"name": "sae-gated-rag-experiments", "stars": 5},
    },
    "updated": "sample data",
}
 
 
# ---------- Main ----------
 
def collect(now):
    """Gather all live data into the README JSON shape."""
    repos = get_repositories()
    latest, last_commit, last_msg = get_latest_push(repos)
    repo_stats = get_repo_stats(repos)
 
    try:
        current, longest = get_contribution_stats()
    except Exception as e:
        print(f"Could not calculate contribution stats: {e}")
        current = longest = None
 
    try:
        commits, issues, prs = get_activity()
    except Exception as e:
        print(f"Could not read activity: {e}")
        commits = issues = prs = None
 
    return {
        "status": get_status(now.hour),
        "weather": get_weather(),
        "github": {
            "top_languages": get_languages(repos),
            "latest_active_repo": latest,
            "last_commit": last_commit,
            "last_commit_message": last_msg,
            "current_streak": current,
            "longest_streak": longest,
            "commits_last_7_days": commits,
            "open_issues": issues,
            "open_prs": prs,
            **repo_stats,
        },
        "updated": now.strftime("%Y-%m-%d %H:%M IST"),
    }
 
 
def main():
    parser = argparse.ArgumentParser(description="Refresh README.md and assets/status.svg")
    parser.add_argument(
        "--test",
        action="store_true",
        help="use sample data (no network, no token) and write to ./test-out/ only",
    )
    args = parser.parse_args()
 
    if args.test:
        out = Path("test-out")
        out.mkdir(exist_ok=True)
        (out / "status.svg").write_text(render_svg(SAMPLE), encoding="utf-8")
        print(f"Wrote {out / 'status.svg'}")
        return
 
    if not TOKEN:
        raise SystemExit("GH_PAT is not set (use --test to try it with sample data)")
 
    now = datetime.now(IST)
    output = collect(now)
 
    # GitHub's image proxy caches by URL, so each refresh gets a new file name.
    ASSETS.mkdir(exist_ok=True)
    for old in ASSETS.glob("status*.svg"):
        old.unlink()
    svg_path = ASSETS / f"status-{now.strftime('%Y%m%d-%H%M')}.svg"
    svg_path.write_text(render_svg(output), encoding="utf-8")
 
    with open(README, "w", encoding="utf-8") as f:
        f.write(f"![Live status]({svg_path.as_posix()})\n\n")
        # Hidden from the rendered page; a website can read this block.
        f.write("<!--\n```json\n")
        json.dump(output, f, indent=2, ensure_ascii=False)
        f.write("\n```\n-->\n")
 
 
if __name__ == "__main__":
    main()

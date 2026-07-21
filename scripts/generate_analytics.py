#!/usr/bin/env python3
"""Generate profile analytics assets for README.

Outputs:
- assets/analytics/stats-purple.svg
- assets/analytics/language-contrib-purple.svg
- assets/analytics/summary.md
- assets/analytics/data.json
- README.md analytics block between ANALYTICS markers
"""

from __future__ import annotations

import json
import os
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Tuple
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
README_PATH = ROOT / "README.md"
ASSETS_DIR = ROOT / "assets" / "analytics"
SUMMARY_PATH = ASSETS_DIR / "summary.md"
DATA_PATH = ASSETS_DIR / "data.json"
STATS_SVG_PATH = ASSETS_DIR / "stats-purple.svg"
LANG_SVG_PATH = ASSETS_DIR / "language-contrib-purple.svg"

ANALYTICS_START = "<!-- ANALYTICS:START -->"
ANALYTICS_END = "<!-- ANALYTICS:END -->"


@dataclass
class AnalyticsData:
    username: str
    generated_at: str
    total_contributions: int
    current_streak: int
    longest_streak: int
    commit_contributions_12m: int
    active_days_12m: int
    selected_repo_count: int
    language_percentages: List[Tuple[str, float]]
    language_repo_counts: Dict[str, int]
    weekday_totals: List[int]


def iso_now() -> datetime:
    return datetime.now(timezone.utc)


def request_json(url: str, token: str, method: str = "GET", body: dict | None = None) -> dict:
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"******",
        "User-Agent": "profile-analytics-generator",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    payload = json.dumps(body).encode("utf-8") if body is not None else None
    req = Request(url, data=payload, headers=headers, method=method)
    with urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def graphql(token: str, query: str, variables: dict) -> dict:
    payload = request_json(
        "https://api.github.com/graphql",
        token,
        method="POST",
        body={"query": query, "variables": variables},
    )
    errors = payload.get("errors") or []
    if errors:
        joined = "; ".join(err.get("message", "GraphQL error") for err in errors)
        raise RuntimeError(joined)
    return payload["data"]


def previous_day(value: date) -> date:
    return value - timedelta(days=1)


def compute_streaks(day_counts: Dict[str, int], through: date) -> Tuple[int, int, int]:
    sorted_days = sorted((date.fromisoformat(k), int(v)) for k, v in day_counts.items() if k <= through.isoformat())
    current = 0
    longest = 0
    running = 0
    active_days = 0

    for _, count in sorted_days:
        if count > 0:
            active_days += 1
            running += 1
            longest = max(longest, running)
        else:
            running = 0

    cursor = through if day_counts.get(through.isoformat(), 0) > 0 else previous_day(through)
    while day_counts.get(cursor.isoformat(), 0) > 0:
        current += 1
        cursor = previous_day(cursor)

    return current, longest, active_days


def collect_contribution_stats(username: str, token: str) -> tuple[int, int, int, int, int, Dict[str, int], List[int]]:
    years_query = """
    query($login: String!) {
      user(login: $login) {
        contributionsCollection {
          contributionYears
          totalCommitContributions
          contributionCalendar {
            weeks {
              contributionDays {
                date
                contributionCount
                weekday
              }
            }
          }
        }
      }
    }
    """

    years_data = graphql(token, years_query, {"login": username})
    user = years_data.get("user")
    if not user:
        raise RuntimeError(f"Could not fetch user {username}")

    contribution_years = user["contributionsCollection"].get("contributionYears", [])
    commit_contributions_12m = int(user["contributionsCollection"].get("totalCommitContributions", 0) or 0)

    day_counts: Dict[str, int] = {}
    total_contributions = 0
    weekday_totals = [0] * 7

    window_query = """
    query($login: String!, $from: DateTime!, $to: DateTime!) {
      user(login: $login) {
        contributionsCollection(from: $from, to: $to) {
          totalContributions
          contributionCalendar {
            weeks {
              contributionDays {
                date
                contributionCount
                weekday
              }
            }
          }
        }
      }
    }
    """

    for yr in sorted(int(y) for y in contribution_years):
        from_dt = datetime(yr, 1, 1, tzinfo=timezone.utc)
        to_dt = datetime(yr, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
        payload = graphql(
            token,
            window_query,
            {
                "login": username,
                "from": from_dt.isoformat().replace("+00:00", "Z"),
                "to": to_dt.isoformat().replace("+00:00", "Z"),
            },
        )

        collection = payload["user"]["contributionsCollection"]
        total_contributions += int(collection.get("totalContributions", 0) or 0)

        for week in collection.get("contributionCalendar", {}).get("weeks", []):
            for day in week.get("contributionDays", []):
                day_counts[day["date"]] = int(day.get("contributionCount", 0) or 0)
                weekday = int(day.get("weekday", 0) or 0)
                if 0 <= weekday < 7:
                    weekday_totals[weekday] += int(day.get("contributionCount", 0) or 0)

    current, longest, active_days = compute_streaks(day_counts, iso_now().date())
    return total_contributions, current, longest, commit_contributions_12m, active_days, day_counts, weekday_totals


def fetch_owned_repositories(username: str, token: str) -> List[dict]:
    repos: List[dict] = []
    page = 1
    while True:
        params = urlencode(
            {
                "type": "owner",
                "sort": "pushed",
                "direction": "desc",
                "per_page": 100,
                "page": page,
            }
        )
        data = request_json(f"https://api.github.com/users/{username}/repos?{params}", token)
        if not data:
            break
        repos.extend(data)
        if len(data) < 100:
            break
        page += 1
    return [r for r in repos if not r.get("fork") and not r.get("archived")]


def select_repositories(repos: List[dict], profile_repo: str, max_repos: int, active_days: int) -> List[dict]:
    cutoff = iso_now() - timedelta(days=active_days)
    selected = []

    for repo in repos:
        pushed = repo.get("pushed_at")
        if not pushed:
            continue
        pushed_at = datetime.fromisoformat(pushed.replace("Z", "+00:00"))
        if pushed_at >= cutoff or repo.get("name") == profile_repo:
            selected.append(repo)

    if not selected:
        selected = repos[:max_repos]

    selected.sort(key=lambda r: (r.get("name") != profile_repo, r.get("pushed_at", "")))
    return selected[:max_repos]


def collect_languages(username: str, token: str, selected_repos: Iterable[dict]) -> tuple[List[Tuple[str, float]], Dict[str, int]]:
    lang_bytes: Dict[str, int] = defaultdict(int)
    lang_repo_counts: Dict[str, int] = defaultdict(int)

    for repo in selected_repos:
        repo_name = repo["name"]
        data = request_json(f"https://api.github.com/repos/{username}/{repo_name}/languages", token)
        for lang, byte_count in sorted(data.items()):
            lang_bytes[lang] += int(byte_count)
            lang_repo_counts[lang] += 1

    total = sum(lang_bytes.values())
    if total == 0:
        return [], dict(lang_repo_counts)

    percentages = sorted(
        [(lang, (byte_count / total) * 100) for lang, byte_count in lang_bytes.items()],
        key=lambda item: (-item[1], item[0]),
    )
    return percentages, dict(lang_repo_counts)


def esc(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def render_stats_svg(data: AnalyticsData) -> str:
    return f"""<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"1000\" height=\"280\" viewBox=\"0 0 1000 280\" role=\"img\" aria-labelledby=\"title desc\">
  <title id=\"title\">Purple GitHub contribution analytics</title>
  <desc id=\"desc\">Total contributions {data.total_contributions}, current streak {data.current_streak}, longest streak {data.longest_streak}, commit contributions in last year {data.commit_contributions_12m}</desc>
  <defs>
    <linearGradient id=\"bg\" x1=\"0\" y1=\"0\" x2=\"1\" y2=\"1\"><stop offset=\"0\" stop-color=\"#10081f\"/><stop offset=\"1\" stop-color=\"#2c1451\"/></linearGradient>
    <linearGradient id=\"accent\" x1=\"0\" y1=\"0\" x2=\"1\" y2=\"0\"><stop offset=\"0\" stop-color=\"#a855f7\"/><stop offset=\"1\" stop-color=\"#d946ef\"/></linearGradient>
    <filter id=\"soft\" x=\"-20%\" y=\"-20%\" width=\"140%\" height=\"140%\"><feGaussianBlur stdDeviation=\"6\"/></filter>
  </defs>
  <rect x=\"1\" y=\"1\" width=\"998\" height=\"278\" rx=\"20\" fill=\"url(#bg)\" stroke=\"#5b2a86\"/>
  <g opacity=\"0.2\"><circle cx=\"130\" cy=\"66\" r=\"26\" fill=\"#f5d0fe\"/><circle cx=\"102\" cy=\"90\" r=\"12\" fill=\"#f5d0fe\"/><circle cx=\"158\" cy=\"90\" r=\"12\" fill=\"#f5d0fe\"/></g>
  <g opacity=\"0.15\"><circle cx=\"910\" cy=\"220\" r=\"30\" fill=\"#ddd6fe\"/><circle cx=\"880\" cy=\"248\" r=\"14\" fill=\"#ddd6fe\"/><circle cx=\"940\" cy=\"248\" r=\"14\" fill=\"#ddd6fe\"/></g>
  <text x=\"40\" y=\"44\" fill=\"#f3e8ff\" font-family=\"Segoe UI,Arial,sans-serif\" font-size=\"22\" font-weight=\"700\">Purple Activity Core</text>
  <text x=\"40\" y=\"66\" fill=\"#c4b5fd\" font-family=\"Segoe UI,Arial,sans-serif\" font-size=\"12\">Updated {esc(data.generated_at)} UTC</text>

  <g font-family=\"Segoe UI,Arial,sans-serif\" fill=\"#f8f5ff\">
    <text x=\"60\" y=\"122\" font-size=\"13\" fill=\"#c4b5fd\">Total Contributions</text>
    <text x=\"60\" y=\"160\" font-size=\"42\" font-weight=\"700\">{data.total_contributions}</text>

    <text x=\"320\" y=\"122\" font-size=\"13\" fill=\"#c4b5fd\">Current Streak</text>
    <text x=\"320\" y=\"160\" font-size=\"42\" font-weight=\"700\">{data.current_streak}d</text>

    <text x=\"540\" y=\"122\" font-size=\"13\" fill=\"#c4b5fd\">Longest Streak</text>
    <text x=\"540\" y=\"160\" font-size=\"42\" font-weight=\"700\">{data.longest_streak}d</text>

    <text x=\"760\" y=\"122\" font-size=\"13\" fill=\"#c4b5fd\">Commit Contributions (12M)</text>
    <text x=\"760\" y=\"160\" font-size=\"42\" font-weight=\"700\">{data.commit_contributions_12m}</text>
  </g>

  <rect x=\"40\" y=\"206\" width=\"920\" height=\"18\" rx=\"9\" fill=\"#2f1c4f\"/>
  <rect x=\"40\" y=\"206\" width=\"{max(20, min(920, int((data.current_streak / max(data.longest_streak, 1)) * 920)))}\" height=\"18\" rx=\"9\" fill=\"url(#accent)\"/>
  <text x=\"40\" y=\"248\" fill=\"#a78bfa\" font-family=\"Segoe UI,Arial,sans-serif\" font-size=\"12\">Streak progress relative to longest streak</text>
</svg>
"""


def wave_path(x: float, y: float, width: float, amplitude: float, waves: int = 3) -> str:
    step = width / (waves * 2)
    path = [f"M {x} {y}"]
    cursor = x
    for _ in range(waves):
        path.append(f"Q {cursor + step/2:.2f} {y - amplitude:.2f} {cursor + step:.2f} {y:.2f}")
        path.append(f"Q {cursor + step*1.5:.2f} {y + amplitude:.2f} {cursor + step*2:.2f} {y:.2f}")
        cursor += step * 2
    return " ".join(path)


def render_language_svg(data: AnalyticsData) -> str:
    top_langs = data.language_percentages[:6] if data.language_percentages else []
    colors = [
        ("#6d28d9", "#a855f7"),
        ("#7c3aed", "#c084fc"),
        ("#8b5cf6", "#d8b4fe"),
        ("#9333ea", "#e879f9"),
        ("#a855f7", "#f0abfc"),
        ("#7e22ce", "#ddd6fe"),
    ]

    bars = []
    legend = []
    base_x = 88
    bar_width = 98
    gap = 24
    for idx, (lang, pct) in enumerate(top_langs):
        x = base_x + idx * (bar_width + gap)
        height = max(26, int((pct / max(top_langs[0][1], 1)) * 230))
        y = 320 - height
        g1, g2 = colors[idx % len(colors)]
        wave = wave_path(x, y + 20, bar_width, 6 + idx)
        bars.append(
            f"""
    <g>
      <rect x=\"{x}\" y=\"{y}\" width=\"{bar_width}\" height=\"{height}\" rx=\"14\" fill=\"url(#lang{idx})\" opacity=\"0.94\"/>
      <path d=\"{wave}\" stroke=\"rgba(255,255,255,0.4)\" stroke-width=\"2\" fill=\"none\"/>
      <text x=\"{x + bar_width/2}\" y=\"{y - 8}\" text-anchor=\"middle\" fill=\"#f5f3ff\" font-size=\"12\" font-family=\"Segoe UI,Arial,sans-serif\">{pct:.1f}%</text>
      <text x=\"{x + bar_width/2}\" y=\"342\" text-anchor=\"middle\" fill=\"#ddd6fe\" font-size=\"11\" font-family=\"Segoe UI,Arial,sans-serif\">{esc(lang)}</text>
    </g>
            """.strip()
        )
        legend.append(f'<linearGradient id="lang{idx}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{g2}"/><stop offset="1" stop-color="{g1}"/></linearGradient>')

    weekday_labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    week_total = sum(data.weekday_totals)
    weekday_rows = []
    for i, label in enumerate(weekday_labels):
        count = data.weekday_totals[i] if i < len(data.weekday_totals) else 0
        pct = (count / week_total * 100) if week_total else 0
        row_y = 74 + i * 24
        weekday_rows.append(
            f'<text x="760" y="{row_y}" fill="#e9d5ff" font-family="Segoe UI,Arial,sans-serif" font-size="12">{label}: {count} ({pct:.1f}%)</text>'
        )

    return f"""<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"1000\" height=\"380\" viewBox=\"0 0 1000 380\" role=\"img\" aria-labelledby=\"title desc\">
  <title id=\"title\">Purple language and contribution analysis</title>
  <desc id=\"desc\">Top languages with flowing purple bars and weekday contribution analysis</desc>
  <defs>
    <linearGradient id=\"bg\" x1=\"0\" y1=\"0\" x2=\"1\" y2=\"1\"><stop offset=\"0\" stop-color=\"#140b28\"/><stop offset=\"1\" stop-color=\"#2d1455\"/></linearGradient>
    {''.join(legend)}
  </defs>
  <rect x=\"1\" y=\"1\" width=\"998\" height=\"378\" rx=\"18\" fill=\"url(#bg)\" stroke=\"#5b2a86\"/>

  <g opacity=\"0.18\"><circle cx=\"70\" cy=\"54\" r=\"16\" fill=\"#f0abfc\"/><circle cx=\"92\" cy=\"74\" r=\"10\" fill=\"#f0abfc\"/><circle cx=\"50\" cy=\"74\" r=\"10\" fill=\"#f0abfc\"/></g>
  <g opacity=\"0.15\"><circle cx=\"952\" cy=\"40\" r=\"14\" fill=\"#ddd6fe\"/><circle cx=\"972\" cy=\"56\" r=\"8\" fill=\"#ddd6fe\"/><circle cx=\"934\" cy=\"56\" r=\"8\" fill=\"#ddd6fe\"/></g>

  <text x=\"40\" y=\"42\" fill=\"#f3e8ff\" font-family=\"Segoe UI,Arial,sans-serif\" font-size=\"22\" font-weight=\"700\">Purple Flow: Language + Contribution Analysis</text>
  <text x=\"40\" y=\"64\" fill=\"#c4b5fd\" font-family=\"Segoe UI,Arial,sans-serif\" font-size=\"12\">Based on selected active repositories ({data.selected_repo_count})</text>

  <line x1=\"720\" y1=\"76\" x2=\"720\" y2=\"350\" stroke=\"#6d28d9\" opacity=\"0.55\"/>
  {''.join(bars)}

  <text x=\"760\" y=\"52\" fill=\"#f5d0fe\" font-family=\"Segoe UI,Arial,sans-serif\" font-size=\"14\" font-weight=\"700\">Contribution cadence by weekday</text>
  {''.join(weekday_rows)}
</svg>
"""


def render_summary_markdown(data: AnalyticsData, fallback_notice: str | None = None) -> str:
    rows = []
    swatches = ["🟣", "🟪", "🟫", "🪻", "💜", "🔮", "✨"]

    for idx, (lang, pct) in enumerate(data.language_percentages[:8]):
        repo_count = data.language_repo_counts.get(lang, 0)
        bar_blocks = max(1, round(pct / 5))
        rows.append(
            f"| {swatches[idx % len(swatches)]} {lang} | {pct:.1f}% | {repo_count} | {'▓' * bar_blocks} |"
        )

    if not rows:
        rows.append("| 🟣 Data unavailable | 0.0% | 0 | ░ |")

    lines = [
        "<div align=\"center\">",
        "  <img src=\"./assets/analytics/stats-purple.svg\" alt=\"Purple GitHub stats card\" width=\"100%\" />",
        "  <br />",
        "  <img src=\"./assets/analytics/language-contrib-purple.svg\" alt=\"Purple language and contribution analysis\" width=\"100%\" />",
        "</div>",
        "",
        "### 🌸 Patterned Language Table",
        "",
        "| Language | Share | Active Repos | Flow |",
        "|---|---:|---:|---|",
        *rows,
        "",
        f"- **Total contributions:** {data.total_contributions}",
        f"- **Current streak:** {data.current_streak} day(s)",
        f"- **Longest streak:** {data.longest_streak} day(s)",
        f"- **Commit contributions (12M):** {data.commit_contributions_12m}",
        "",
        f"<sub>Last updated: {data.generated_at} UTC · Auto-refreshed daily at 03:00 UTC via GitHub Actions.</sub>",
        "",
        "<sub>Generated by `scripts/generate-analytics.py` using GitHub API data (`GITHUB_TOKEN`).</sub>",
    ]

    if fallback_notice:
        lines.extend(["", f"<sub>⚠️ {fallback_notice}</sub>"])

    return "\n".join(lines).strip() + "\n"


def replace_analytics_block(readme_text: str, markdown: str) -> str:
    if ANALYTICS_START not in readme_text or ANALYTICS_END not in readme_text:
        raise RuntimeError("README is missing analytics markers")

    start_index = readme_text.index(ANALYTICS_START) + len(ANALYTICS_START)
    end_index = readme_text.index(ANALYTICS_END)
    return readme_text[:start_index] + "\n" + markdown + readme_text[end_index:]


def fallback_data(username: str) -> AnalyticsData:
    return AnalyticsData(
        username=username,
        generated_at=iso_now().strftime("%Y-%m-%d %H:%M"),
        total_contributions=0,
        current_streak=0,
        longest_streak=0,
        commit_contributions_12m=0,
        active_days_12m=0,
        selected_repo_count=0,
        language_percentages=[],
        language_repo_counts={},
        weekday_totals=[0, 0, 0, 0, 0, 0, 0],
    )


def write_outputs(data: AnalyticsData, error_message: str | None = None) -> None:
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    STATS_SVG_PATH.write_text(render_stats_svg(data), encoding="utf-8")
    LANG_SVG_PATH.write_text(render_language_svg(data), encoding="utf-8")

    fallback_notice = None
    if error_message:
        fallback_notice = "Live GitHub API data was temporarily unavailable during generation; placeholders were emitted and will be refreshed on the next successful run."
    summary = render_summary_markdown(data, fallback_notice)

    SUMMARY_PATH.write_text(summary, encoding="utf-8")

    DATA_PATH.write_text(
        json.dumps(
            {
                "username": data.username,
                "generated_at": data.generated_at,
                "total_contributions": data.total_contributions,
                "current_streak": data.current_streak,
                "longest_streak": data.longest_streak,
                "commit_contributions_12m": data.commit_contributions_12m,
                "active_days_12m": data.active_days_12m,
                "selected_repo_count": data.selected_repo_count,
                "language_percentages": [[k, round(v, 4)] for k, v in data.language_percentages],
                "language_repo_counts": data.language_repo_counts,
                "weekday_totals": data.weekday_totals,
                "error": error_message,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    readme = README_PATH.read_text(encoding="utf-8")
    updated = replace_analytics_block(readme, summary)
    README_PATH.write_text(updated, encoding="utf-8")


def build_analytics(username: str, token: str) -> AnalyticsData:
    total_contribs, current, longest, commit_12m, active_days_12m, _day_counts, weekday_totals = collect_contribution_stats(username, token)

    repos = fetch_owned_repositories(username, token)
    profile_repo = os.getenv("PROFILE_REPO", username)
    max_repos = max(1, int(os.getenv("MAX_REPOS", "12")))
    active_repo_days = max(1, int(os.getenv("ACTIVE_REPO_DAYS", "365")))
    selected_repos = select_repositories(repos, profile_repo, max_repos, active_repo_days)

    language_percentages, language_repo_counts = collect_languages(username, token, selected_repos)

    return AnalyticsData(
        username=username,
        generated_at=iso_now().strftime("%Y-%m-%d %H:%M"),
        total_contributions=total_contribs,
        current_streak=current,
        longest_streak=longest,
        commit_contributions_12m=commit_12m,
        active_days_12m=active_days_12m,
        selected_repo_count=len(selected_repos),
        language_percentages=language_percentages,
        language_repo_counts=language_repo_counts,
        weekday_totals=weekday_totals,
    )


def main() -> int:
    username = os.getenv("GITHUB_USER", "RaktheshTG")
    token = os.getenv("GITHUB_TOKEN", "")

    if not token:
        fallback = fallback_data(username)
        write_outputs(fallback, "GITHUB_TOKEN is not set")
        print("Generated fallback analytics (missing GITHUB_TOKEN)")
        return 0

    try:
        analytics = build_analytics(username, token)
        write_outputs(analytics)
        print(f"Generated analytics for @{username}")
        return 0
    except Exception as exc:  # noqa: BLE001
        fallback = fallback_data(username)
        write_outputs(fallback, str(exc))
        print(f"Generated fallback analytics due to API error: {exc}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())

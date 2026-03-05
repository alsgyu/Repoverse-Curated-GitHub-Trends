#!/usr/bin/env python3
import argparse
import json
import math
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
HEADERS = {"Accept": "application/vnd.github.v3+json"}
if GITHUB_TOKEN:
    HEADERS["Authorization"] = f"token {GITHUB_TOKEN}"

SECTION_QUERIES = {
    "llm_engines": [
        "llm inference server",
        "model serving llm",
        "llm runtime",
        "inference engine transformer",
        "llm deployment",
    ],
    "agents": [
        "ai agent framework",
        "autonomous agent",
        "multi-agent orchestration",
        "browser automation agent",
        "tool calling agent",
    ],
    "cli_tools": [
        "cli ai assistant",
        "terminal ai coding",
        "developer tools ai",
        "code assistant cli",
        "git ai assistant",
    ],
    "art_vision": [
        "diffusion image generation",
        "text-to-image",
        "image generation model",
        "video generation",
        "stable diffusion",
    ],
    "frameworks": [
        "machine learning framework",
        "llm framework",
        "nlp framework",
        "deep learning library",
        "agent framework",
    ],
}


def github_get(url, params=None):
    try:
        resp = requests.get(url, headers=HEADERS, params=params, timeout=20)
    except requests.RequestException as exc:
        raise RuntimeError(f"Network error: {exc}") from exc
    return resp


def search_repositories(query, min_stars, pushed_after, pages=2, per_page=100, sleep_on_rate_limit=False):
    base = "https://api.github.com/search/repositories"
    qualifiers = f"archived:false fork:false pushed:>{pushed_after} stars:>={min_stars}"
    q = f"{query} {qualifiers}".strip()
    results = []
    for page in range(1, pages + 1):
        params = {
            "q": q,
            "sort": "stars",
            "order": "desc",
            "per_page": per_page,
            "page": page,
        }
        resp = github_get(base, params=params)
        if resp.status_code != 200:
            if resp.status_code == 403 and "rate limit" in resp.text.lower():
                if sleep_on_rate_limit:
                    reset = int(resp.headers.get("X-RateLimit-Reset", "0"))
                    wait = max(0, reset - int(datetime.now(timezone.utc).timestamp()) + 2)
                    if wait > 0:
                        print(f"Rate limit hit. Sleeping {wait}s until reset...")
                        import time
                        time.sleep(wait)
                        continue
                raise RuntimeError("GitHub API rate limit exceeded. Set GITHUB_TOKEN or try later.")
            raise RuntimeError(f"GitHub API error {resp.status_code}: {resp.text[:200]}")
        data = resp.json()
        items = data.get("items", [])
        if not items:
            break
        results.extend(items)
        remaining = int(resp.headers.get("X-RateLimit-Remaining", "1"))
        if remaining <= 1:
            break
    return results


def trend_score(repo, now, recency_days):
    stars = repo.get("stargazers_count", 0)
    created_at = datetime.fromisoformat(repo["created_at"].replace("Z", "+00:00"))
    pushed_at = datetime.fromisoformat(repo["pushed_at"].replace("Z", "+00:00"))
    age_days = max((now - created_at).days, 30)
    stars_per_day = stars / age_days
    recency = max(0.0, (recency_days - (now - pushed_at).days) / recency_days)
    return (stars_per_day * 100.0) + (recency * 50.0) + (math.log10(stars + 1) * 10.0)


def update_projects(projects_path, per_section, min_stars, recency_days, mode, pages, sleep_on_rate_limit, sections):
    data = json.loads(projects_path.read_text(encoding="utf-8"))
    now = datetime.now(timezone.utc)
    pushed_after = (now - timedelta(days=recency_days)).date().isoformat()

    used = set()
    target_sections = sections or list(data.keys())
    for section in target_sections:
        meta = data.get(section)
        if not meta:
            print(f"Skipping unknown section: {section}")
            continue
        queries = SECTION_QUERIES.get(section, [])
        if not queries:
            continue
        candidates = {}
        for q in queries:
            for repo in search_repositories(q, min_stars, pushed_after, pages=pages, sleep_on_rate_limit=sleep_on_rate_limit):
                full_name = repo.get("full_name")
                if not full_name:
                    continue
                if full_name not in candidates:
                    candidates[full_name] = repo

        scored = []
        for repo in candidates.values():
            score = trend_score(repo, now, recency_days)
            scored.append((score, repo))
        scored.sort(key=lambda x: x[0], reverse=True)

        selected = []
        for _, repo in scored:
            full_name = repo["full_name"]
            if full_name in used:
                continue
            selected.append({"url_path": full_name})
            used.add(full_name)
            if len(selected) >= per_section:
                break

        if mode == "merge":
            existing = meta.get("repos", []) or []
            existing_set = {r.get("url_path") for r in existing if r.get("url_path")}
            merged = existing + [r for r in selected if r["url_path"] not in existing_set]
            meta["repos"] = merged[:per_section]
        else:
            meta["repos"] = selected

        print(f"{section}: selected {len(meta['repos'])} repos")
        projects_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    projects_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Update projects.json with trending GitHub repos.")
    parser.add_argument("--per-section", type=int, default=50)
    parser.add_argument("--min-stars", type=int, default=200)
    parser.add_argument("--recency-days", type=int, default=180)
    parser.add_argument("--mode", choices=["replace", "merge"], default="replace")
    parser.add_argument("--pages", type=int, default=2, help="Search pages per query (each page costs 1 request).")
    parser.add_argument("--sleep-on-rate-limit", action="store_true")
    parser.add_argument("--sections", type=str, default="", help="Comma-separated section keys to update.")
    args = parser.parse_args()

    base_dir = Path(__file__).resolve().parent
    projects_path = base_dir / "projects.json"

    sections = [s.strip() for s in args.sections.split(",") if s.strip()]
    update_projects(
        projects_path=projects_path,
        per_section=args.per_section,
        min_stars=args.min_stars,
        recency_days=args.recency_days,
        mode=args.mode,
        pages=args.pages,
        sleep_on_rate_limit=args.sleep_on_rate_limit,
        sections=sections,
    )
    print("projects.json updated. Run `python3 update_readme.py` to regenerate README.")


if __name__ == "__main__":
    main()

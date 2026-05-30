#!/usr/bin/env python3
"""Search proxy/tunnel rules across upstream repos.

Usage:
  scripts/search.py -q openai
  scripts/search.py -q github --pager
  scripts/search.py -q microsoft --refresh
"""

import argparse
import difflib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

CACHE_DIR = Path(__file__).parent / ".cache"
INDEX_TTL = 86400  # 24 h
MAX_AUTO_LINES = 200

REPOS = {
    "ios_rule_script": {
        "display": "blackmatrix7/ios_rule_script",
        "raw_base": "https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master",
    },
    "v2fly_dlc": {
        "display": "v2fly/domain-list-community",
        "raw_base": "https://raw.githubusercontent.com/v2fly/domain-list-community/master",
    },
}

TOKEN = os.environ.get("GITHUB_TOKEN")


# ── helpers ──────────────────────────────────────────────────────────

def gh(url: str) -> dict:
    req = urllib.request.Request(url)
    if TOKEN:
        req.add_header("Authorization", f"Bearer {TOKEN}")
    req.add_header("User-Agent", "subconverter-rule-search")
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def dl(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "subconverter-rule-search"})
    with urllib.request.urlopen(req) as r:
        return r.read().decode("utf-8")


# scoring strategy: exact > prefix > substring > word-match > difflib
WORD_RE = re.compile(r"[a-zA-Z][a-z]*|[0-9]+")


def score_name(query: str, name: str) -> float:
    q = query.lower()
    n = name.lower()
    if n == q:
        return 100
    if q in n or n in q:
        return 80
    return 0


# ── index ────────────────────────────────────────────────────────────

def _load_build_index(cache: Path, key: str, builder) -> dict:
    p = cache / f"index_{key}.json"
    if p.exists() and time.time() - p.stat().st_mtime < INDEX_TTL:
        return json.loads(p.read_text())
    print(f"[index] 更新 {REPOS[key]['display']} 索引 ...", file=sys.stderr)
    data = builder()
    cache.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False))
    return data


def build_ios():
    tree = gh("https://api.github.com/repos/blackmatrix7/ios_rule_script/git/trees/master?recursive=1")
    pat = re.compile(r"^rule/(Clash|Surge|Loon|QuantumultX|Shadowrocket)/([^/]+)/\2\.list$")
    idx: dict[str, dict[str, list[str]]] = {}
    for e in tree.get("tree", []):
        m = pat.match(e["path"])
        if m:
            pl, nm = m.groups()
            idx.setdefault(nm, {}).setdefault(pl, []).append(e["path"])
    return idx


def build_v2fly():
    tree = gh("https://api.github.com/repos/v2fly/domain-list-community/git/trees/master?recursive=1")
    idx: dict[str, str] = {}
    for e in tree.get("tree", []):
        p = e["path"]
        if p.startswith("data/") and e["type"] == "blob":
            nm = p[5:]
            if "/" not in nm:
                idx[nm] = p
    return idx


# ── fetch ────────────────────────────────────────────────────────────

def fetch_ios(cache: Path, cat: str, platforms: dict) -> tuple[list[str], list[Path], list[str]]:
    d = cache / "files" / "ios" / cat
    d.mkdir(parents=True, exist_ok=True)
    all_lines: list[str] = []
    local_files: list[Path] = []
    source_paths: list[str] = []
    for pl, paths in platforms.items():
        lf = d / f"{pl}.list"
        if not lf.exists():
            url = f"{REPOS['ios_rule_script']['raw_base']}/{paths[0]}"
            try:
                lf.write_text(dl(url))
            except Exception as e:
                print(f"  [warn] {paths[0]}: {e}", file=sys.stderr)
                continue
        local_files.append(lf)
        source_paths.extend(paths)
        all_lines.extend(lf.read_text().splitlines())

    # dedup non-comment lines
    seen: set[str] = set()
    out: list[str] = []
    for line in all_lines:
        s = line.rstrip()
        if s and not s.startswith("#") and s not in seen:
            seen.add(s)
            out.append(s)
    return out, local_files, source_paths


def fetch_v2fly(cache: Path, name: str, path: str) -> tuple[list[str], list[Path], list[str]]:
    d = cache / "files" / "v2fly"
    d.mkdir(parents=True, exist_ok=True)
    lf = d / name
    if not lf.exists():
        url = f"{REPOS['v2fly_dlc']['raw_base']}/{path}"
        try:
            lf.write_text(dl(url))
        except Exception as e:
            print(f"  [warn] {path}: {e}", file=sys.stderr)
            return [], [], []
    lines = [l.rstrip() for l in lf.read_text().splitlines()
             if l.strip() and not l.strip().startswith("#")]
    return lines, [lf], [path]


# ── output ───────────────────────────────────────────────────────────

def _flush_pager(tmp: str):
    try:
        subprocess.run(["bat", "--paging=always", tmp], check=False)
    except FileNotFoundError:
        subprocess.run(["batcat", "--paging=always", tmp], check=False)


def display_pager(results):
    fd, tmp = tempfile.mkstemp(suffix=".txt", prefix="rule_search_")
    prev = None
    with os.fdopen(fd, "w") as f:
        for rid, cat, lines, cached, source_paths in results:
            if rid != prev:
                f.write(f"\n{'='*60}\n📦 {REPOS[rid]['display']}\n{'='*60}\n\n")
                prev = rid
            f.write(f"## {cat}  ({len(lines)} 条)\n")
            for sp, cf in zip(source_paths, cached):
                f.write(f"  📄 {sp}\n")
                f.write(f"     {cf.resolve().as_uri()}\n")
            f.write("\n")
            for l in lines:
                f.write(l + "\n")
            f.write("\n")
    _flush_pager(tmp)
    os.unlink(tmp)


def display_stdout(results):
    """Print results with smart truncation. Return number of lines printed."""
    prev = None
    printed = 0
    # pre‑compute total for all entries for truncation decision
    grand = sum(len(lines) for _, _, lines, _, _ in results)
    truncate = grand > MAX_AUTO_LINES

    for rid, cat, lines, cached, source_paths in results:
        if rid != prev:
            if prev is not None:
                print()
            print(f"{'='*60}\n📦 {REPOS[rid]['display']}\n{'='*60}")
            prev = rid

        if truncate and printed >= MAX_AUTO_LINES:
            # already printed enough across earlier results
            continue

        print(f"\n## {cat}  ({len(lines)} 条rule)")
        for sp, cf in zip(source_paths, cached):
            print(f"  📄 {sp}")
            print(f"     {cf.resolve().as_uri()}")
        quota = MAX_AUTO_LINES - printed if truncate else len(lines)
        for l in lines[:quota]:
            print(f"  {l}")
        printed += min(quota, len(lines))
        remaining_cat = len(lines) - quota
        if remaining_cat > 0:
            print(f"\n  … 本分类剩余 {remaining_cat} 条已截断")

    if truncate:
        hidden = grand - printed
        print(f"\n  共 {hidden} 条rule未显示（超过 {MAX_AUTO_LINES} 行自动截断）")
        print(f"  使用 --pager 参数可通过 bat 分页浏览")
    elif printed == 0:
        print("  (空)")


# ── main ─────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="搜索 upstream 规则集")
    ap.add_argument("-q", "--query", required=True)
    ap.add_argument("-p", "--pager", action="store_true", help="用 bat 分页")
    ap.add_argument("--refresh", action="store_true", help="清索引缓存")
    args = ap.parse_args()

    if args.refresh:
        for p in [CACHE_DIR / "index_ios.json", CACHE_DIR / "index_v2fly.json"]:
            if p.exists():
                p.unlink()
                print(f"  [cache] 清除 {p.name}", file=sys.stderr)

    idx_ios = _load_build_index(CACHE_DIR, "ios_rule_script", build_ios)
    idx_v2fly = _load_build_index(CACHE_DIR, "v2fly_dlc", build_v2fly)

    # score categories, keep > 0
    ios_scored = [(s, n) for s, n in ((score_name(args.query, n), n) for n in idx_ios) if s > 0]
    v2_scored = [(s, n) for s, n in ((score_name(args.query, n), n) for n in idx_v2fly) if s > 0]
    ios_scored.sort(key=lambda x: -x[0])
    v2_scored.sort(key=lambda x: -x[0])

    if not ios_scored and not v2_scored:
        print(f"无匹配「{args.query}」的分类")
        return

    results: list[tuple[str, str, list[str], list[Path], list[str]]] = []

    # fetch – limit to top 5 per repo, skip score < 50 if >3 higher matches exist
    for score, name in ios_scored[:5]:
        lines, cached, source_paths = fetch_ios(CACHE_DIR, name, idx_ios[name])
        results.append(("ios_rule_script", name, lines, cached, source_paths))

    for score, name in v2_scored[:5]:
        lines, cached, source_paths = fetch_v2fly(CACHE_DIR, name, idx_v2fly[name])
        results.append(("v2fly_dlc", name, lines, cached, source_paths))

    if args.pager:
        display_pager(results)
    else:
        display_stdout(results)


if __name__ == "__main__":
    main()

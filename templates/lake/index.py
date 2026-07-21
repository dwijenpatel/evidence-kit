#!/usr/bin/env python3
"""Regenerate XREF.md — tag index, backlinks, shared sources — for a lake corpus.

Deterministic, stdlib-only. Part of the evidence-kit lake profile; run after every
pass:  python3 index.py        (rewrite XREF.md)
       python3 index.py --check  (exit 1 if XREF.md is stale; used by the guard)
"""
import os
import re
import sys
from collections import defaultdict
from urllib.parse import parse_qsl, urlencode, urlsplit

ROOT = os.path.dirname(os.path.abspath(__file__))
FENCE = re.compile(r"\A---[ \t]*\r?\n(.*?)^---[ \t]*\r?$", re.DOTALL | re.MULTILINE)
FM_TAGS = re.compile(r"^tags:\s*\[([^\]]*)\]", re.MULTILINE)
LINK = re.compile(r"\[[^\]]*\]\(([^)#\s]+?)(?:#[^)]*)?\)")
URL = re.compile(r"https?://[^\s)\]>|\"']+")
ARXIV_PATH = re.compile(r"^/(?:abs|pdf)/(\d{4}\.\d{4,5})(?:v\d+)?(?:\.pdf)?/?$",
                         re.IGNORECASE)
PROSE_ARXIV = re.compile(r"\barXiv[:\s]+(\d{4}\.\d{4,5})", re.IGNORECASE)
DROP_QUERY_PREFIX = "utm_"
DROP_QUERY_EXACT = {"ref", "source"}
SKIP_FILES = {"XREF.md"}
SKIP_DIRS = {"tests", "mirrors"}          # mirrors enter via MANIFEST parsing only


def canon_url(u):
    """Canonicalize a URL to a shared-source key: lowercase scheme+host, strip
    'www.', drop #fragment, drop utm_*/ref/source query params, strip one trailing
    slash. arXiv abs/pdf URLs (any version) collapse to 'arxiv:<id>'."""
    parts = urlsplit(u)
    host = parts.netloc.lower()
    if host.startswith("www."):
        host = host[len("www."):]
    if host == "arxiv.org":
        m = ARXIV_PATH.match(parts.path)
        if m:
            return f"arxiv:{m.group(1)}"
    path = parts.path
    if path.endswith("/"):
        path = path[:-1]
    kept = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
            if not k.lower().startswith(DROP_QUERY_PREFIX)
            and k.lower() not in DROP_QUERY_EXACT]
    key = host + path
    if kept:
        key += "?" + urlencode(kept)
    return key


def walk_md():
    out = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        rel = os.path.relpath(dirpath, ROOT)
        dirnames[:] = sorted(d for d in dirnames if not d.startswith(".")
                             and not (rel == "." and d in SKIP_DIRS))
        for name in sorted(filenames):
            if name.endswith(".md") and name not in SKIP_FILES:
                p = os.path.join(rel, name) if rel != "." else name
                out.append(p.replace(os.sep, "/"))
    return out


def manifests():
    out = []
    for dirpath, dirnames, filenames in os.walk(os.path.join(ROOT, "mirrors")):
        dirnames.sort()
        for name in sorted(filenames):
            if name == "MANIFEST.md":
                out.append(os.path.relpath(os.path.join(dirpath, name), ROOT)
                           .replace(os.sep, "/"))
    return out


def domain(path):
    parts = path.split("/")
    if parts[0] == "mirrors" and len(parts) > 2:
        return parts[1]
    return parts[0] if len(parts) > 1 else "(root)"


def subtopic(path):
    parts = path.split("/")
    return "/".join(parts[:2]) if len(parts) > 1 else "(root)"


def build():
    tag_map = defaultdict(list)             # tag -> [path]
    backlinks = defaultdict(list)           # target -> [source]
    url_map = defaultdict(set)              # canonical key -> {non-mirror subtopic}
    variants = defaultdict(set)             # canonical key -> {raw form seen}
    mirrored = set()                        # canonical keys also cited from a MANIFEST
    for path in walk_md():
        with open(os.path.join(ROOT, path), encoding="utf-8") as fh:
            body = fh.read()
        fm = FENCE.match(body)
        fm_text = fm.group(1) if fm else ""
        m = FM_TAGS.search(fm_text)
        if m:
            for tag in (x.strip() for x in m.group(1).split(",") if x.strip()):
                tag_map[tag].append(path)
        base = os.path.dirname(path)
        for lm in LINK.finditer(body):
            target = lm.group(1)
            if target.startswith(("http://", "https://", "mailto:", "lake:")):
                continue
            resolved = (target.lstrip("/") if target.startswith("/")
                        else os.path.normpath(os.path.join(base, target)))
            backlinks[resolved.replace(os.sep, "/")].append(path)
        sub = subtopic(path)
        for u in URL.findall(body):
            raw = u.rstrip(".,;")
            key = canon_url(raw)
            url_map[key].add(sub)
            variants[key].add(raw)
        for pm in PROSE_ARXIV.finditer(body):
            key = f"arxiv:{pm.group(1)}"
            url_map[key].add(sub)
            variants[key].add(pm.group(0).strip())
    for mpath in manifests():
        with open(os.path.join(ROOT, mpath), encoding="utf-8") as fh:
            mbody = fh.read()
        for u in URL.findall(mbody):
            raw = u.rstrip(".,;")
            key = canon_url(raw)
            mirrored.add(key)
            variants[key].add(raw)
        for pm in PROSE_ARXIV.finditer(mbody):
            key = f"arxiv:{pm.group(1)}"
            mirrored.add(key)
            variants[key].add(pm.group(0).strip())
    return tag_map, backlinks, url_map, variants, mirrored


def render():
    tag_map, backlinks, url_map, variants, mirrored = build()
    L = ["---", "type: Generated Index",
         "title: \"XREF — tags, backlinks, shared sources (generated)\"",
         "description: \"Generated by index.py; do not edit. Regenerate after every pass.\"",
         "---", "", "# XREF (generated — do not edit)", "",
         "## Tag index", ""]
    for tag in sorted(tag_map):
        docs = sorted(set(tag_map[tag]))
        doms = sorted({domain(d) for d in docs})
        cross = " **[cross-domain]**" if len(doms) > 1 else ""
        L.append(f"- `{tag}`{cross}: " + " · ".join(f"[{d}]({d})" for d in docs))
    L += ["", "## Backlinks (cross-domain edges first)", ""]
    edges = []
    for target in sorted(backlinks):
        for src in sorted(set(backlinks[target])):
            edges.append((domain(src) != domain(target), src, target))
    for cross, src, target in sorted(edges, key=lambda e: (not e[0], e[1], e[2])):
        mark = " **[cross-domain]**" if cross else ""
        L.append(f"- [{src}]({src}) → [{target}]({target}){mark}")
    L += ["", "## Shared sources (URL in ≥2 subtopics)", ""]
    for key in sorted(url_map):
        subs = sorted(url_map[key])
        if len(subs) > 1:
            forms = variants.get(key, set())
            forms_note = f" *({len(forms)} forms)*" if len(forms) > 1 else ""
            mirror_note = " [mirrored]" if key in mirrored else ""
            L.append(f"- {key} — {', '.join(subs)}{forms_note}{mirror_note}")
    return "\n".join(L) + "\n"


def main():
    fresh = render()
    idx = os.path.join(ROOT, "XREF.md")
    current = None
    if os.path.exists(idx):
        with open(idx, encoding="utf-8") as fh:
            current = fh.read()
    if "--check" in sys.argv:
        sys.exit(0 if current == fresh else 1)
    with open(idx, "w", encoding="utf-8") as fh:
        fh.write(fresh)
    print("XREF.md regenerated")


if __name__ == "__main__":
    main()

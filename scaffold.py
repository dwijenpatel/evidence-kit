#!/usr/bin/env python3
"""Instantiate a new evidence corpus from the kit's templates.

  python3 scaffold.py --topic "Solid-state batteries" --slug ssb \
      --out ../ssb-corpus --consumer "who has skin in the game, and for what"

Copies templates/corpus/ (substituting {{TOPIC}} {{SLUG}} {{CONSUMER}} {{DATE}}
{{KIT_COMMIT}} {{KIT_PATH}}), installs the guard test + its config, and prints next steps.
Refuses a non-empty target. Templates named _*.tmpl are pass-time templates
(e.g. the subtopic README) and are not instantiated here.
"""

import argparse
import datetime
import os
import shutil
import subprocess
import sys

KIT = os.path.dirname(os.path.abspath(__file__))

PROFILES = {
    # skip_top: top-level template dirs not copied · overlay: templates/<name>/ copied
    # after the main walk (overwrites collisions) · default_min_docs: guard floor that
    # passes on a bare scaffold of this profile
    "standalone": {"skip_top": set(), "overlay": None, "default_min_docs": 6},
    "lake": {"skip_top": {"external", "internal", "distilled"}, "overlay": "lake",
             "default_min_docs": 3},
    "project": {"skip_top": {"external"}, "overlay": "project", "default_min_docs": 6},
}


def kit_commit():
    try:
        return subprocess.run(
            ["git", "-C", KIT, "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unversioned"


def render_tree(src_root, out, subs, emitted_md, skip_top=frozenset()):
    for dirpath, dirnames, filenames in os.walk(src_root):
        rel = os.path.relpath(dirpath, src_root)
        top = rel.split(os.sep)[0]
        if top in skip_top:
            dirnames[:] = []
            continue
        for name in filenames:
            if name.startswith("_"):
                continue  # pass-time template, not scaffold-time
            with open(os.path.join(dirpath, name), encoding="utf-8") as fh:
                body = fh.read()
            for key, val in subs.items():
                body = body.replace(key, val)
            dest_name = name[:-5] if name.endswith(".tmpl") else name
            dest_dir = os.path.join(out, "" if rel == "." else rel)
            os.makedirs(dest_dir, exist_ok=True)
            with open(os.path.join(dest_dir, dest_name), "w", encoding="utf-8") as fh:
                fh.write(body)
            if dest_name.endswith(".md"):
                rel_md = dest_name if rel == "." else f"{rel}/{dest_name}"
                if rel_md not in emitted_md:
                    emitted_md.append(rel_md.replace(os.sep, "/"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--topic", required=True, help="human-readable topic name")
    ap.add_argument("--slug", required=True, help="kebab-case short name")
    ap.add_argument("--out", required=True, help="corpus directory to create")
    ap.add_argument("--consumer", required=True,
                    help="who has skin in the game (a decision surface damaged if a claim "
                         "is wrong, required to cite Tier-A rows; the curious-reader "
                         "audience is automatic — 'audience-only for now' is honest)")
    ap.add_argument("--profile", choices=sorted(PROFILES), default="standalone",
                    help="corpus profile: standalone (default, self-contained), "
                         "lake (shared external evidence), project (internal+distilled "
                         "citing a lake)")
    ap.add_argument("--min-docs", type=int, default=None,
                    help="guard: minimum tracked markdown files (default: per-profile "
                         "floor that passes on a bare scaffold)")
    ap.add_argument("--lake-root", default=None,
                    help="project profile: absolute path to the evidence lake this "
                         "corpus cites (written to corpus_guard.json as lake_root)")
    args = ap.parse_args()

    if args.profile == "project" and not args.lake_root:
        ap.error("--lake-root is required for --profile project")

    profile = PROFILES[args.profile]
    min_docs = args.min_docs if args.min_docs is not None else profile["default_min_docs"]

    out = os.path.abspath(os.path.expanduser(args.out))
    if os.path.exists(out) and os.listdir(out):
        sys.exit(f"refusing: {out} exists and is not empty")

    # --topic and --consumer land inside double-quoted YAML frontmatter values;
    # these characters would make every scaffolded doc unparseable as OKF.
    for flag, val in (("--topic", args.topic), ("--consumer", args.consumer)):
        if any(c in val for c in '"\\\n'):
            sys.exit(f"refusing: {flag} may not contain double quotes, backslashes, "
                     "or newlines (it is embedded in YAML frontmatter)")

    subs = {
        "{{TOPIC}}": args.topic,
        "{{SLUG}}": args.slug,
        "{{CONSUMER}}": args.consumer,
        "{{DATE}}": datetime.date.today().isoformat(),
        "{{KIT_COMMIT}}": kit_commit(),
        "{{KIT_PATH}}": KIT,
    }

    emitted_md = []  # every scaffolded doc is load-bearing: this becomes the guard's list
    render_tree(os.path.join(KIT, "templates", "corpus"), out, subs, emitted_md,
                skip_top=profile["skip_top"])
    if profile["overlay"]:
        render_tree(os.path.join(KIT, "templates", profile["overlay"]), out, subs,
                    emitted_md)
    if args.profile == "lake":
        os.makedirs(os.path.join(out, "mirrors"), exist_ok=True)

    os.makedirs(os.path.join(out, "tests"), exist_ok=True)
    shutil.copy(os.path.join(KIT, "templates", "tests", "test_reference.py"),
                os.path.join(out, "tests", "test_reference.py"))
    guard_cfg = {
        "profile": args.profile,
        "required": sorted(emitted_md),
        "min_markdown_files": min_docs,
    }
    if args.profile == "project":
        guard_cfg["lake_root"] = os.path.abspath(os.path.expanduser(args.lake_root))
    with open(os.path.join(out, "tests", "corpus_guard.json"), "w", encoding="utf-8") as fh:
        import json
        json.dump(guard_cfg, fh, indent=2)
        fh.write("\n")

    print(f"corpus scaffolded at {out} (kit commit {subs['{{KIT_COMMIT}}']})")
    print("next steps:")
    print("  1. fill the domain decay table in distilled/README.md")
    print("  2. declare the mirror location in README.md")
    print("  3. git init && git add -A && git commit")
    print("  4. python3 -m unittest tests.test_reference -q")


if __name__ == "__main__":
    main()

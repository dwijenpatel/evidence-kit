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


def kit_commit():
    try:
        return subprocess.run(
            ["git", "-C", KIT, "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unversioned"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--topic", required=True, help="human-readable topic name")
    ap.add_argument("--slug", required=True, help="kebab-case short name")
    ap.add_argument("--out", required=True, help="corpus directory to create")
    ap.add_argument("--consumer", required=True,
                    help="who has skin in the game (a decision surface damaged if a claim "
                         "is wrong, required to cite Tier-A rows; the curious-reader "
                         "audience is automatic — 'audience-only for now' is honest)")
    ap.add_argument("--min-docs", type=int, default=6,
                    help="guard: minimum tracked markdown files (default 6; a bare "
                         "scaffold has 8, so the guard passes before the first pass)")
    args = ap.parse_args()

    out = os.path.abspath(os.path.expanduser(args.out))
    if os.path.exists(out) and os.listdir(out):
        sys.exit(f"refusing: {out} exists and is not empty")

    subs = {
        "{{TOPIC}}": args.topic,
        "{{SLUG}}": args.slug,
        "{{CONSUMER}}": args.consumer,
        "{{DATE}}": datetime.date.today().isoformat(),
        "{{KIT_COMMIT}}": kit_commit(),
        "{{KIT_PATH}}": KIT,
    }

    src_root = os.path.join(KIT, "templates", "corpus")
    for dirpath, _dirnames, filenames in os.walk(src_root):
        rel = os.path.relpath(dirpath, src_root)
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

    os.makedirs(os.path.join(out, "tests"), exist_ok=True)
    shutil.copy(os.path.join(KIT, "templates", "tests", "test_reference.py"),
                os.path.join(out, "tests", "test_reference.py"))
    with open(os.path.join(out, "tests", "corpus_guard.json"), "w", encoding="utf-8") as fh:
        import json
        json.dump({
            "required": ["README.md", "index.md", "terminology.md", "distilled/README.md",
                         "distilled/external.md", "distilled/internal.md",
                         "external/README.md", "internal/README.md"],
            "min_markdown_files": args.min_docs,
        }, fh, indent=2)
        fh.write("\n")

    print(f"corpus scaffolded at {out} (kit commit {subs['{{KIT_COMMIT}}']})")
    print("next steps:")
    print("  1. fill the domain decay table in distilled/README.md")
    print("  2. declare the mirror location in README.md")
    print("  3. git init && git add -A && git commit")
    print("  4. python3 -m unittest tests.test_reference -q")


if __name__ == "__main__":
    main()

"""Resolve and verify archive citations (oaos2/archive/cite.py) without the dashboard.

Resolve one citation (prints the cited object and, for events, its verbatim text):
  PYTHONPATH="$PWD" python scripts/cite.py "cite: <run_ref> · ev <id> · seq 47 · handoff · officer_a · day 2 · sha256:0123abcd4567"

Verify every citation — and every quotation on the same line as one — in documents:
  PYTHONPATH="$PWD" python scripts/cite.py --check library/tasks/budget_execution/DESIGN_LOG.md docs/experiments/*.md

Options: --runs <root> (default runs/). Exit status 1 when any citation or quote fails.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    from oaos2.archive.cite import parse_citation, resolve, verify_document

    runs_root = Path("runs")
    args = list(argv)
    if "--runs" in args:
        i = args.index("--runs")
        runs_root = Path(args[i + 1])
        del args[i:i + 2]
    if not args:
        print(__doc__)
        return 2
    if args[0] == "--check":
        failed = 0
        for doc in args[1:]:
            text = Path(doc).read_text()
            results = verify_document(runs_root, text)
            n_bad = sum(1 for r in results if not r["ok"] or any(not q["found"] for q in r["quotes"]))
            failed += n_bad
            print(f"{doc}: {len(results)} citation(s), {n_bad} problem(s)")
            for r in results:
                if not r["ok"]:
                    print(f"  line {r['line']}: {r['problem']}\n    {r['raw']}")
                for q in r["quotes"]:
                    if not q["found"]:
                        print(f"  line {r['line']}: quotation not found verbatim in the cited object:\n    \"{q['text'][:100]}\"")
        return 1 if failed else 0
    parsed = parse_citation(" ".join(args))
    if parsed is None:
        print("not a citation (expected the `cite: …` format)")
        return 2
    res = resolve(runs_root, parsed)
    if not res["ok"]:
        print(f"UNRESOLVED: {res['problem']}")
        return 1
    print(f"run dir: {res['run_dir']}")
    if parsed["kind"] == "event":
        print(f"dashboard: http://127.0.0.1:8722/run/{parsed['run_ref']}/event/{parsed['event_id']}")
    print(json.dumps(res["object"], indent=2, sort_keys=True)[:6000])
    if res["texts"]:
        print("\n--- text ---")
        for t in res["texts"]:
            if len(t) > 40:
                print(t[:2000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

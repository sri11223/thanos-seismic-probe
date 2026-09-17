#!/usr/bin/env python3
"""Aggregate the 8 per-slot rollout results into the Thanos difficulty verdict."""
import glob, json, os, statistics, sys, pathlib

def main():
    files = sorted(glob.glob("results/**/result_*.json", recursive=True)) + sorted(glob.glob("results/result_*.json"))
    rows = []
    for f in files:
        try: rows.append(json.load(open(f)))
        except Exception as e: print("skip", f, e)
    # dedupe by slot
    by_slot = {}
    for r in rows: by_slot[str(r.get("slot"))] = r
    rows = [by_slot[k] for k in sorted(by_slot)]
    print("=== per-slot results ===")
    for r in rows:
        print("  slot %-3s reward=%-5s num_turns=%-5s asst=%-4s %ss %s" % (
            r.get("slot"), r.get("reward"), r.get("num_turns"), r.get("assistant_turns"),
            r.get("seconds"), ("ERR "+str(r.get("error"))) if r.get("error") else ""))
    rewards = [r["reward"] for r in rows if r.get("reward") is not None]
    passes = sum(1 for x in rewards if x >= 1.0)
    n = len(rewards)
    turns = [r["num_turns"] or r.get("assistant_turns") or 0 for r in rows if r.get("reward") is not None]
    asst = [r.get("assistant_turns") or 0 for r in rows if r.get("reward") is not None]
    median_turns = statistics.median(sorted(turns)) if turns else 0
    median_asst = statistics.median(sorted(asst)) if asst else 0
    print()
    print("=== VERDICT ===")
    print("graded rollouts:", n, "of", len(rows))
    print("pass@%d: %d / %d" % (n, passes, n))
    print("median num_turns:", median_turns, " median assistant_turns:", median_asst)
    diff_ok = 1 <= passes <= 6 if n == 8 else 1 <= passes <= 2
    lh_ok = median_asst > 80
    print("difficulty band (target 1-2 of 8, accept 1-6):", "PASS" if (1 <= passes <= 2) else ("WIDE-OK" if 1 <= passes <= 6 else ("TOO_EASY" if passes>6 else "TOO_HARD")))
    print("long-horizon (median assistant_turns > 80):", "PASS" if lh_ok else "FAIL")
    summary = {"pass_at_n": passes, "n": n, "median_num_turns": median_turns,
               "median_assistant_turns": median_asst,
               "difficulty": ("TOO_EASY" if passes>6 else "TOO_HARD" if passes<1 else "IN_BAND" if passes<=2 else "WIDE"),
               "long_horizon_ok": lh_ok, "rows": rows}
    pathlib.Path("verdict.json").write_text(json.dumps(summary, indent=2))
    print()
    print("wrote verdict.json")

if __name__ == "__main__":
    main()

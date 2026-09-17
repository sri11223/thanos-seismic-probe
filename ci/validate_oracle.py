#!/usr/bin/env python3
"""CI oracle+NOP validation via harbor Docker. Oracle must pass (reward 1), NOP must fail."""
import json, os, pathlib, subprocess, sys

def run(task, agent, job):
    cmd = ["harbor","run","-p",str(task),"--agent",agent,"--job-name",job,"-o","jobs","-k","1","-n","1","-y"]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=5400)
    sys.stdout.write(p.stdout[-3000:]); sys.stderr.write(p.stderr[-3000:])
    reward = None
    for trial in sorted((pathlib.Path("jobs")/job).glob("*__*")):
        rw = trial/"verifier"/"reward.txt"
        if rw.exists():
            try: reward = float(rw.read_text().strip())
            except ValueError: pass
    return reward

def main():
    task = sys.argv[1]
    orc = run(task, "oracle", "ci-oracle")
    nop = run(task, "nop", "ci-nop")
    print("ORACLE reward:", orc)
    print("NOP reward:", nop)
    ok = (orc == 1.0) and (nop is None or nop == 0.0)
    pathlib.Path("oracle_verdict.json").write_text(json.dumps({"oracle":orc,"nop":nop,"ok":ok}))
    if not ok:
        print("VALIDATION FAILED: oracle must be 1.0 and NOP must be 0/none"); sys.exit(1)
    print("VALIDATION PASSED")

if __name__ == "__main__":
    main()

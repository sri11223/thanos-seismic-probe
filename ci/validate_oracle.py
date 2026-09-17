#!/usr/bin/env python3
import glob, json, os, pathlib, subprocess, sys
def run(task, agent, job):
    cmd = ["harbor","run","-p",str(task),"--agent",agent,"--job-name",job,"-o","jobs","-k","1","-n","1","-y","--verifier-include-logs","**/*"]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=5400)
    sys.stdout.write(p.stdout[-2000:]); sys.stderr.write(p.stderr[-2000:])
    reward = None
    for trial in sorted((pathlib.Path("jobs")/job).glob("*__*")):
        rw = trial/"verifier"/"reward.txt"
        if rw.exists():
            try: reward = float(rw.read_text().strip())
            except ValueError: pass
        for ctrf in trial.glob("verifier/**/ctrf.json"):
            try:
                data = json.load(open(ctrf))
                for t in data.get("results",{}).get("tests",[]):
                    if t.get("status") != "passed":
                        print("FAIL[%s] %s :: %s" % (agent, t.get("name"), str(t.get("message"))[:600]))
            except Exception as e:
                print("ctrf read err", e)
        for lg in trial.glob("verifier/**/*.txt"):
            if lg.name == "reward.txt": continue
            txt = lg.read_text(encoding="utf-8", errors="replace")
            if "Error" in txt or "assert" in txt or "FAIL" in txt:
                print("--- %s (tail) ---" % lg.name); print(txt[-1500:])
    return reward
def main():
    task = sys.argv[1]
    orc = run(task, "oracle", "ci-oracle")
    nop = run(task, "nop", "ci-nop")
    print("ORACLE reward:", orc); print("NOP reward:", nop)
    ok = (orc == 1.0) and (nop is None or nop == 0.0)
    pathlib.Path("oracle_verdict.json").write_text(json.dumps({"oracle":orc,"nop":nop,"ok":ok}))
    if not ok:
        print("VALIDATION FAILED"); sys.exit(1)
    print("VALIDATION PASSED")
if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""One-rollout probe runner for CI, with an in-process stall killer.
Runs harbor (claude-code + OpenRouter gate model). A watcher thread finds the agent container for
this slot's job and kills a stalled 'claude --verbose' whose session jsonl is idle > STALL_SEC,
letting harbor retry instead of burning the full timeout on a hung model stream."""
import argparse, json, os, pathlib, subprocess, sys, threading, time

GATE_MODEL = os.environ.get("GATE_MODEL", "tencent/hy4-preview")
STALL_SEC = int(os.environ.get("STALL_SEC", "300"))

def docker(*args, timeout=60):
    try:
        return subprocess.run(["docker", *args], capture_output=True, text=True, timeout=timeout)
    except Exception:
        return None

def stall_watcher(job, stop):
    while not stop.is_set():
        r = docker("ps", "--format", "{{.Names}}")
        names = (r.stdout.split() if r and r.stdout else [])
        for c in names:
            if "main" not in c:  # harbor task container ends with -main-1
                continue
            script = ("f=$(find /logs -name '*.jsonl' -path '*projects*' 2>/dev/null | head -1); "
                      "if [ -n \"$f\" ]; then age=$(( $(date +%s) - $(stat -c %Y \"$f\") )); "
                      "if [ $age -gt " + str(STALL_SEC) + " ]; then pkill -9 -f 'claude --verbose'; echo killed; fi; fi")
            docker("exec", c, "sh", "-c", script)
        stop.wait(120)

import re, shutil
def ci_task_copy(task):
    tt = os.environ.get("CI_TASK_TIMEOUT")
    if not tt:
        return task
    src = pathlib.Path(task)
    dst = src.parent / (src.name + "_ci%s" % os.getpid())
    if dst.exists():
        return str(dst)
    shutil.copytree(src, dst)
    toml = dst / "task.toml"
    t = toml.read_text()
    t = re.sub(r"(\[agent\]\s*\ntimeout_sec\s*=\s*)\d+", r"\g<1>%s" % tt, t)
    assert ("timeout_sec = %s" % tt) in t, "CI_TASK_TIMEOUT regex did not apply"
    toml.write_text(t)
    return str(dst)

def run_one(task, slot, jobs_dir, setup_mult):
    key = os.environ["OPENROUTER_API_KEY"]
    task = ci_task_copy(task)
    job = "gate-slot%s" % slot
    cmd = [
        "harbor", "run", "-p", str(task), "--agent", "claude-code", "--model", GATE_MODEL,
        "--ae", "ANTHROPIC_BASE_URL=https://openrouter.ai/api",
        "--ae", "ANTHROPIC_AUTH_TOKEN=%s" % key,
        "--ae", "ANTHROPIC_API_KEY=",
        "--ae", "ANTHROPIC_DEFAULT_OPUS_MODEL=%s" % GATE_MODEL,
        "--ae", "ANTHROPIC_DEFAULT_SONNET_MODEL=%s" % GATE_MODEL,
        "--ae", "ANTHROPIC_DEFAULT_HAIKU_MODEL=%s" % GATE_MODEL,
        "--agent-setup-timeout-multiplier", str(setup_mult),
        "--agent-timeout-multiplier", os.environ.get("AGENT_TIMEOUT_MULT", "0.09"),
        "--max-retries", "3",
        "--verifier-include-logs", "**/*",
        "--job-name", job, "-o", str(jobs_dir), "-k", "1", "-n", "1", "-y",
    ]
    print("RUN slot", slot, flush=True)
    stop = threading.Event()
    t = threading.Thread(target=stall_watcher, args=(job, stop), daemon=True); t.start()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=int(os.environ.get("ROLLOUT_TIMEOUT", "10800")))
        sys.stdout.write(proc.stdout[-4000:]); sys.stderr.write(proc.stderr[-2000:])
    finally:
        stop.set()
    return pathlib.Path(jobs_dir) / job

def collect_fails(trial):
    fails = []
    for ctrf in trial.glob("verifier/**/ctrf.json"):
        try:
            data = json.load(open(ctrf))
            for t in data.get("results", {}).get("tests", []):
                if t.get("status") != "passed":
                    fails.append(t.get("name"))
        except Exception:
            pass
    return fails

def harvest(job_dir):
    reward = turns = None; asst = 0; fails = []
    for trial in sorted(pathlib.Path(job_dir).glob("*__*")):
        fails = collect_fails(trial) or fails
        rw = trial / "verifier" / "reward.txt"
        if rw.exists():
            try: reward = float(rw.read_text().strip())
            except ValueError: pass
        log = trial / "agent" / "claude-code.txt"
        if log.exists():
            lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
            for line in reversed(lines):
                if '"num_turns"' in line:
                    try: turns = json.loads(line).get("num_turns")
                    except Exception: pass
                    break
            asst = sum(1 for l in lines if '"type":"assistant"' in l)
        if asst == 0:
            for jl in trial.glob("agent/sessions/projects/*/*.jsonl"):
                asst = max(asst, sum(1 for l in jl.read_text(encoding="utf-8", errors="replace").splitlines() if '"type":"assistant"' in l))
    return reward, turns, asst, fails

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", required=True); ap.add_argument("--slot", required=True)
    ap.add_argument("--jobs-dir", default="jobs"); ap.add_argument("--setup-multiplier", default="4")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    t0 = time.time(); err = None
    try:
        jd = run_one(a.task, a.slot, a.jobs_dir, a.setup_multiplier)
        reward, turns, asst, fails = harvest(jd)
    except Exception as e:
        reward, turns, asst, fails = None, None, 0, []; err = repr(e)
    res = {"slot": a.slot, "reward": reward, "num_turns": turns, "assistant_turns": asst, "failed_tests": fails,
           "seconds": round(time.time()-t0, 1), "error": err}
    pathlib.Path(a.out).write_text(json.dumps(res, indent=2), encoding="utf-8")
    print("RESULT:", json.dumps(res), flush=True)

if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""One-rollout probe runner for CI. Runs harbor on the task with the gate model via OpenRouter,
then extracts reward + assistant turn count into result_<slot>.json."""
import argparse, json, os, pathlib, subprocess, sys, time

GATE_MODEL = os.environ.get("GATE_MODEL", "tencent/hy4-preview")

def run_one(task, slot, jobs_dir, setup_mult):
    key = os.environ["OPENROUTER_API_KEY"]
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
        "--job-name", job, "-o", str(jobs_dir), "-k", "1", "-n", "1", "-y",
    ]
    print("RUN:", " ".join(c if "AUTH_TOKEN" not in c else "ANTHROPIC_AUTH_TOKEN=***" for c in cmd), flush=True)
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=int(os.environ.get("ROLLOUT_TIMEOUT", "18000")))
    sys.stdout.write(proc.stdout[-4000:]); sys.stderr.write(proc.stderr[-4000:])
    return pathlib.Path(jobs_dir) / job

def harvest(job_dir):
    reward = None; turns = None; asst = 0
    for trial in sorted(pathlib.Path(job_dir).glob("*__*")):
        rw = trial / "verifier" / "reward.txt"
        if rw.exists():
            try: reward = float(rw.read_text().strip())
            except ValueError: pass
        # turns: prefer claude-code.txt num_turns; else count assistant in session jsonl
        log = trial / "agent" / "claude-code.txt"
        if log.exists():
            for line in reversed(log.read_text(encoding="utf-8", errors="replace").splitlines()):
                if '"num_turns"' in line:
                    try: turns = json.loads(line).get("num_turns")
                    except Exception: pass
                    break
            asst = sum(1 for l in log.read_text(encoding="utf-8", errors="replace").splitlines() if '"type":"assistant"' in l)
        if asst == 0:
            for jl in trial.glob("agent/sessions/projects/*/*.jsonl"):
                asst = max(asst, sum(1 for l in jl.read_text(encoding="utf-8", errors="replace").splitlines() if '"type":"assistant"' in l))
    return reward, turns, asst

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", required=True)
    ap.add_argument("--slot", required=True)
    ap.add_argument("--jobs-dir", default="jobs")
    ap.add_argument("--setup-multiplier", default="4")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    t0 = time.time()
    err = None
    try:
        jd = run_one(a.task, a.slot, a.jobs_dir, a.setup_multiplier)
        reward, turns, asst = harvest(jd)
    except Exception as e:
        reward, turns, asst = None, None, 0; err = repr(e)
    res = {"slot": a.slot, "reward": reward, "num_turns": turns, "assistant_turns": asst,
           "seconds": round(time.time()-t0, 1), "error": err}
    pathlib.Path(a.out).write_text(json.dumps(res, indent=2), encoding="utf-8")
    print("RESULT:", json.dumps(res), flush=True)

if __name__ == "__main__":
    sys.exit(main())

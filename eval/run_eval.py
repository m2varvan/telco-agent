"""
Unified Evaluation Entry Point
Delegates execution to eval/runner/run_agent_eval.py
"""
import sys
import subprocess

def main():
    cmd = [sys.executable, "eval/runner/run_agent_eval.py"] + sys.argv[1:]
    res = subprocess.run(cmd)
    sys.exit(res.returncode)

if __name__ == "__main__":
    main()

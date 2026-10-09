#!/usr/bin/env bash
# usage: capture_service_env.sh <pid> <out.json>   -- records the service process' non-secret configuration (secrets redacted to presence flags)
PID="$1"; OUT="$2"
ps eww -p "$PID" 2>/dev/null | tr ' ' '\n' | grep -E "^[A-Z_0-9]*(COMQUTOR|WEEK2|LLM|DEEPSEEK|OPENAI|ANTHROPIC|TRADINGAGENTS)[A-Z_0-9]*=" \
 | sed -E 's/^([A-Z_0-9]*(KEY|TOKEN|SECRET|PASSWORD)[A-Z_0-9]*)=.*/\1=<redacted-present>/; s#(postgresql[^:]*://[^:]+:)[^@]+@#\1<redacted>@#' | sort > "$OUT.txt"
/Users/xiangmao/COMQUTOR-Alpha-/.venv/bin/python - "$PID" "$OUT" <<'PY'
import json,subprocess,sys
pid,out=sys.argv[1],sys.argv[2]
env=dict(l.split("=",1) for l in open(out+".txt").read().splitlines() if "=" in l)
info=subprocess.run(["ps","-o","pid=,ppid=,lstart=,command=","-p",pid],capture_output=True,text=True).stdout.strip()
json.dump({"pid":pid,"ps":info,"env":env},open(out,"w"),indent=1,sort_keys=True)
print("captured",len(env),"variables for pid",pid)
PY

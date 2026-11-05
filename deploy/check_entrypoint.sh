#!/bin/sh
# Start the judge, wait until it answers, then run the check.
#
#   karimi-check:  no arguments, KARIMI_JOB_ID set by the batch job that started it
#   karimi-sweep:  --sweep (no judge needed, so none is started)
set -eu

if [ "${1:-}" != "--sweep" ]; then
    # Same server settings as at calibration: context 8192, temperature 0 per request.
    /opt/llama/llama-server -m /models/judge.gguf --host 127.0.0.1 --port 8080 -c 8192 \
        -t "$(nproc)" > /tmp/llama.log 2>&1 &
    i=0
    until curl -sf http://127.0.0.1:8080/health > /dev/null; do
        i=$((i + 1))
        if [ "$i" -gt 180 ]; then
            echo '{"severity":"ERROR","event":"karimi_judge_not_started"}'
            tail -20 /tmp/llama.log
            exit 1
        fi
        sleep 1
    done
fi

exec python -m karimi_normalise.check "$@"

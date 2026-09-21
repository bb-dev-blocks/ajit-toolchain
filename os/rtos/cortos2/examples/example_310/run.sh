#!/usr/bin/env bash
# Headless C-model run. serial_in.txt is written after "Enabled serial".

cd "$(dirname "$0")/cortos_build"
fifo=$(mktemp -u)
log=$(mktemp)
mkfifo "$fifo"
cleanup() { rm -f "$fifo" "$log"; }
trap cleanup EXIT

# stdbuf on the shell is inherited by the model (LD_PRELOAD).
stdbuf -oL -eL ./run_cmodel.sh <"$fifo" >"$log" 2>&1 &
pid=$!
exec 3>"$fifo"
sent=0
deadline=$((SECONDS + 180))
while kill -0 "$pid" 2>/dev/null; do
  if [[ $sent -eq 0 ]] && grep -q "Enabled serial" "$log"; then
    python3 -c 'import os,sys; os.write(int(sys.argv[1]), b"q\n")' 3
    sent=1
  fi
  if (( SECONDS >= deadline )); then
    kill "$pid" 2>/dev/null || true
    break
  fi
  sleep 0.2
done
wait "$pid" || true
cat "$log"
if [[ $sent -eq 0 ]] || ! grep -q "BYE(1)" "$log"; then
  echo "CoRTOS: ERROR: example_310 did not receive q and print BYE(1)" >&2
  exit 1
fi
exit 0

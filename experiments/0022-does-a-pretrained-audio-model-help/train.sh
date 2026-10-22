#!/usr/bin/env bash
# LoRA fine-tune Stable Audio 3 on the balanced American Crow bout set.
#
# --duration is the argument that matters and the one with a dangerous default.
# sample_size is derived from it as (duration * sample_rate // ds_ratio) * ds_ratio,
# and the default is 380 SECONDS. Our bouts top out at 3.0 s, so the default would
# pad every clip into a 380-second window and spend the whole run on silence.
# Five seconds leaves room for the model's silence extension without that.
#
# SMOKE=1 runs 50 steps to prove the pipeline and measure throughput before
# committing to the real thing.
set -euo pipefail

SA3="${SA3:-/home/ben/Code/stable-audio-3}"
DATA="${DATA:-/home/ben/Code/cawtalker/data/sa3-lora/american-crow}"
OUT="${OUT:-/home/ben/Code/cawtalker/data/sa3-lora/checkpoints}"
MODEL="${MODEL:-small-sfx-base}"

STEPS="${STEPS:-4000}"
BATCH="${BATCH:-4}"
if [ "${SMOKE:-0}" = "1" ]; then
  STEPS=50
  OUT="$OUT-smoke"
fi

mkdir -p "$OUT"
cd "$SA3"

echo "model=$MODEL steps=$STEPS batch=$BATCH clips=$(ls "$DATA"/*.wav | wc -l)"

exec uv run python scripts/train_lora.py \
  --model "$MODEL" \
  --data_dir "$DATA" \
  --save_dir "$OUT" \
  --duration 5.0 \
  --rank 16 \
  --adapter_type dora-rows \
  --base_precision bf16 \
  --lr 1e-4 \
  --steps "$STEPS" \
  --batch_size "$BATCH" \
  --checkpoint_every 500 \
  --demo_every 500 \
  --logger csv \
  --name crow-lora

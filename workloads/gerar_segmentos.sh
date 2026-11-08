#!/usr/bin/env bash
# Gera os segmentos de vídeo sintéticos servidos pelo Nginx.
# Se o ffmpeg estiver instalado, corta um .mp4 real; senão, usa bytes aleatórios
# com o mesmo tamanho (o servidor só entrega bytes, então o efeito sobre a CPU é equivalente).
set -euo pipefail
DIR="${1:-$(dirname "$0")/video}"
N_SEG="${2:-20}"
TAM_KB="${3:-400}"   # ~400 KB por segmento (cerca de 1,6 Mbps para segmentos de 2 s)
mkdir -p "$DIR"
for i in $(seq 1 "$N_SEG"); do
  head -c "$((TAM_KB * 1024))" /dev/urandom > "$DIR/seg_$(printf '%03d' "$i").ts"
done
echo "gerados $N_SEG segmentos de ${TAM_KB} KB em $DIR"

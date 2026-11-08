#!/usr/bin/env bash
# Execução automatizada do piloto, do zero, em Ubuntu (ou qualquer Linux com root).
# Uso:  sudo bash executar_piloto.sh [repeticoes] [duracao_s]
#       (opcional) sudo ESPECTADORES=20 INTERVALO=0.2 NIVEIS="0 1 2 4" bash executar_piloto.sh 3 8
set -euo pipefail
cd "$(dirname "$0")"
REP="${1:-3}"
DUR="${2:-8}"

echo "[1/4] dependências"
if ! command -v nginx >/dev/null || ! command -v stress-ng >/dev/null; then
  apt-get update -qq && apt-get install -y -qq nginx stress-ng python3-pandas python3-matplotlib
fi
# (o piloto usa uma instância própria do Nginx na porta 8080; não precisa parar o serviço do sistema)

echo "[2/4] segmentos de vídeo"
[ -d workloads/video ] && [ "$(ls workloads/video | wc -l)" -ge 20 ] || bash workloads/gerar_segmentos.sh workloads/video 20 400

echo "[3/4] rodada (próxima rodada livre)"
R=1; while ls resultados/brutos/rodada${R}_*.csv >/dev/null 2>&1; do R=$((R+1)); done
python3 orquestrador/run_experimento.py --rodada "$R" --repeticoes "$REP" --duracao "$DUR" \
        --warmup 2 --cooldown 2 --espectadores "${ESPECTADORES:-50}" --intervalo "${INTERVALO:-0.2}" ${NIVEIS:+--niveis $NIVEIS} ${CTL_ALTO:+--ctl-alto $CTL_ALTO} ${CTL_BAIXO:+--ctl-baixo $CTL_BAIXO}

echo "[4/4] análise e gráficos"
python3 analise/analisar.py --rodada "$R"
echo "pronto: resultados/brutos/ e analise/saida/"

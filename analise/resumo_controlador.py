#!/usr/bin/env python3
"""Resume o sinal de espera na fila registrado pelo controlador, por execução.
Uso: python3 analise/resumo_controlador.py resultados/brutos/rodada50_*.csv
Serve para calibrar --ctl-alto / --ctl-baixo (rode antes com --ctl-observar)."""
import pathlib
import sys
import pandas as pd

for caminho in sys.argv[1:]:
    d = pd.read_csv(caminho)
    base = pathlib.Path(caminho).parent / "controlador"
    print(f"{'run_id':10s} {'nivel':>5s} {'mediana':>8s} {'p90':>8s}   (espera do Nginx na fila, fração do tempo)")
    for _, r in d.sort_values("nivel_contencao").iterrows():
        f = base / f"{r.run_id}.csv"
        if not f.exists():
            continue
        s = pd.read_csv(f)["sinal"]
        print(f"{r.run_id:10s} {int(r.nivel_contencao):5d} {s.median():8.4f} {s.quantile(.9):8.4f}")

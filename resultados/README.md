# resultados

CSVs brutos de cada rodada em `brutos/`. Nunca sobrescrever: um arquivo novo por rodada (`rodada1_2026-10-16.csv`), com o `_meta.json` da rodada (semente, argumentos, kernel). As latências de cada requisição ficam em `brutos/amostras/<run_id>.csv.gz`.

Colunas do CSV: rodada, run_id, ordem, modo, nivel_contencao, rep, inicio_iso, duracao_s, n_req, n_falhas, thr_req_s, thr_MBps, lat_media_ms, lat_mediana_ms, lat_p95_ms, lat_p99_ms, lat_max_ms, reb_20ms/50ms/100ms (fração de segmentos acima do limiar), cpu_servidor_pct, ctx_vol, ctx_invol, psi_some_us_por_s, cpu_host_pct, loadavg1, descartada, obs.

Rodada 1: container de 2 vCPUs, 48 execuções (calibração). Rodada 2: máquina Linux do Davi, 16 execuções (teste rápido). **Rodada 3: máquina Linux do Davi, 48 execuções (piloto principal).** Ver `docs/relatorio_piloto.md`.

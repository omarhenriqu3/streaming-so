# configs

- `nginx.conf.tpl`: template do Nginx (um worker, porta 8080). O orquestrador substitui `@RUNDIR@`, `@PORTA@` e `@VIDEODIR@` e grava a configuração final em `/tmp/so_run/`.

Os parâmetros dos modos de isolamento (núcleo 0 para o servidor, pesos de cgroup 4096/128 em v1 e 400/10 em v2, `nice -15`) estão no topo de `executar()` em `orquestrador/run_experimento.py`.

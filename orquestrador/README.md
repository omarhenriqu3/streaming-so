# orquestrador

`run_experimento.py` executa o experimento de forma automatizada. Para cada combinação (modo de isolamento × nível de contenção × repetição), **em ordem sorteada** (semente gravada em `resultados/brutos/rodadaN_<data>_meta.json`):

1. inicia o Nginx (1 worker) com o isolamento do modo já aplicado;
2. inicia o `stress-ng` com N processos;
3. espera o warm-up e lê os contadores do SO;
4. roda o cliente sintético (`workloads/cliente_streaming.py`) por `--duracao` segundos;
5. lê os contadores de novo, calcula as métricas e grava **uma linha no CSV**; as latências individuais vão para `resultados/brutos/amostras/<run_id>.csv.gz`;
6. encerra tudo e espera o cooldown.

## Modos de isolamento

| Modo | Como é aplicado |
| --- | --- |
| `sem_isolamento` | nenhum (referência) |
| `affinity` | Nginx fixado no núcleo 0 (`sched_setaffinity`); o `stress-ng` fica nos demais núcleos |
| `cgroup` | Nginx em um grupo com peso de CPU alto (v1: `cpu.shares=4096`; v2: `cpu.weight=400`) e o `stress-ng` em outro com peso baixo (128 / 10) |
| `prioridade` | Nginx com `nice -15` |

Detecta cgroup v1 ou v2 automaticamente. **Só o caminho v1 foi exercitado até agora** (container do piloto); o v2 (Ubuntu do Davi) está implementado, mas precisa ser conferido na primeira execução na VM.

## Métricas coletadas por execução

Vazão (req/s, MB/s), latência (média, mediana, p95, p99, máx.), fração de segmentos acima de 20/50/100 ms (proxy de rebuffering), CPU do worker (`/proc/PID/stat`), context switches voluntários e involuntários (`/proc/PID/status`), PSI de CPU (`/proc/pressure/cpu`, delta de `some total`), uso de CPU do host (`/proc/stat`) e carga média.

> `perf stat` não foi usado: o `perf` do container não corresponde ao kernel em uso. Os contadores de context switches vêm de `/proc/PID/status`, que são os mesmos que o `perf stat -e context-switches` reporta por processo.

## Uso

```bash
sudo bash executar_piloto.sh 3 8      # instala dependências, roda, analisa (3 repetições, 8 s)
# ou diretamente:
sudo python3 orquestrador/run_experimento.py --rodada 1 --repeticoes 3 --duracao 8
```

Nunca sobrescreve: se o CSV da rodada já existe, aborta.

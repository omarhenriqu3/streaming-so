# Relatório do piloto (3º marco)

Objetivo do marco: mostrar que o experimento **pode ser executado e medido** e identificar problemas metodológicos antes da coleta definitiva.

## O que foi executado

| Rodada | Onde | O que | Papel |
| --- | --- | --- | --- |
| 1 | Container Linux, 2 vCPUs | 48 execuções, 50 espectadores | Calibração inicial do pipeline |
| 2 | Máquina Linux do Davi, 12 CPUs lógicas | 16 execuções (1 repetição, 4 s) | Teste rápido |
| **3** | **Máquina Linux do Davi, 12 CPUs lógicas** | **48 execuções (16 configurações × 3 repetições, 8 s, 20 espectadores)** | **Piloto principal (resultados abaixo)** |

- **Rodada 3:** ordem sorteada (semente 1792270469), 2 s de warm-up e 2 s de cooldown, kernel 7.0.0-38-generic. **48 de 48 execuções válidas**, nenhuma falha de requisição.
- **Carga:** 20 espectadores sintéticos, um segmento de 400 KB a cada 0,2 s cada (≈ 100 req/s, ≈ 40 MB/s) contra um Nginx com 1 worker.
- **Dados:** `resultados/brutos/rodada3_2026-10-17.csv` (uma linha por execução), `resultados/brutos/amostras/` (latência de cada requisição), `analise/saida/resumo_rodada3.csv` (médias e desvios).
- **Gráficos:** `analise/saida/fig1_latencia_vs_contencao.png` e `fig2_indicadores_so.png` (gerados da rodada 3).
- **Ambiente:** ver `docs/ambiente.md`.

## Resultado preliminar da rodada 3 (média de 3 repetições, ms)

| Modo | Mediana n=0 | n=2 | n=4 | n=8 | p99 n=0 | n=2 | n=4 | n=8 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Sem isolamento | 3,38 | 0,70 | 0,72 | 1,48 | 14,7 | 5,9 | 7,0 | 22,1 |
| CPU affinity | 1,94 | 0,54 | 0,77 | 1,16 | 16,5 | 8,0 | 6,7 | 12,8 |
| cgroups | 4,58 | 0,62 | 0,66 | 1,06 | 21,0 | 7,1 | 5,1 | 9,9 |
| Prioridade (nice) | 3,75 | 0,67 | 0,77 | 0,77 | 17,1 | 8,0 | 7,0 | 10,6 |

Uso médio de CPU do computador por nível de contenção: 32% (n=0), 37% (n=2), 54% (n=4), 85% (n=8). A vazão ficou em ≈ 97–98 req/s em todas as configurações, e a fração de segmentos acima de 20 ms (proxy de rebuffering) ficou ≤ 2%.

**Leitura (apenas indicativa, n=3):** a contenção só deixa sinal claro com 8 processos. Nesse nível, o p99 sem isolamento (22,1 ms) é cerca de duas vezes o dos demais modos (9,9–12,8 ms), os context switches involuntários do servidor são 647 contra 183–374, e o PSI é o mais alto (10,5% contra 7,2–9,8%). Isso é compatível com a hipótese de que isolamento reduz a degradação, mas as repetições se sobrepõem (p99 sem isolamento: 35,2 / 19,5 / 11,5 ms; cgroups: 14,0 / 9,4 / 6,3 ms), então **ainda não é conclusivo**.

## Problemas metodológicos encontrados e o que fazer na coleta definitiva

| # | Problema | Evidência no piloto | Ação proposta |
| --- | --- | --- | --- |
| 1 | **A linha de base (n=0) é pior que n=2.** | Mediana 3,4 ms em n=0 contra 0,6–0,7 ms em n=2, nos quatro modos, e nas rodadas 2 e 3. O CPU do computador estava em 32% mesmo sem `stress-ng`. | Provável efeito de gerenciamento de energia (frequência/estados de ociosidade) e/ou atividade em segundo plano. Fixar o governador em `performance`, fechar outros programas, registrar `cpupower frequency-info` e repetir o n=0 depois de um aquecimento. |
| 2 | **Os níveis de contenção não acompanham o número de CPUs.** Com 12 CPUs lógicas, n=2 e n=4 ocupam só 37% e 54%. | Só n=8 (85% da CPU) separa os modos. | Definir os níveis como fração do número de CPUs (por exemplo 0, metade, 1× e 2× o número de CPUs) e registrar o número de CPUs de cada máquina. |
| 3 | **Carga leve demais.** O servidor usa 2–7% de CPU e a vazão é ditada pelo ritmo do cliente, então ela não pode mostrar degradação. | Vazão ≈ 98 req/s em todas as 16 configurações; rebuffering ≤ 2%. | Medir também a vazão máxima (cliente em laço fechado, por exemplo `wrk`) e definir o limiar de rebuffering a partir da latência de referência. |
| 4 | **Poucas repetições e muita variação.** | Coeficiente de variação do p99: mediana 0,25, máximo 0,55; o p99 de n=8 sem isolamento variou de 11,5 a 35,2 ms. | Pelo menos 10 repetições, 30–60 s por execução, mediana e intervalo interquartil, teste não paramétrico (Mann–Whitney). |
| 5 | **O cliente Python compete pela mesma CPU.** | Com 50 espectadores na VM, o p99 foi 1214 ms e a vazão 140 req/s sem nenhuma contenção. | Cliente em C (`wrk`/`ab`) e/ou fixado em um núcleo próprio. Conferir com `$request_time` do Nginx. |
| 6 | **PSI é do sistema inteiro.** | O PSI inclui o próprio `stress-ng` e o cliente. | Usar o PSI do cgroup do servidor (`cpu.pressure`) ou `run_delay` do worker em `/proc/PID/schedstat`. |
| 7 | **O modo affinity mistura dois efeitos:** fixa o servidor no núcleo 0 e tira o `stress-ng` desse núcleo. | Implementação em `executar()`. | Separar em "affinity só do servidor" e "isolamento de CPU", ou renomear o modo. |
| 8 | **Máquinas diferentes dão resultados diferentes.** | Container de 2 vCPUs (rodada 1) e computador de 12 CPUs (rodada 3) têm saturação e valores bem diferentes. | Fazer toda a coleta definitiva em **uma só máquina**, com o mesmo estado (tomada, programas fechados) e registrar tudo em `docs/ambiente.md`. Decidir com o professor se será a VM ou o Linux do Davi. |
| 9 | **A VM do VirtualBox ficou instável sob carga.** | Na VM do Omar (4 vCPUs, 2,6 GB), o computador travou em E/S (carga 27, 48% de espera de disco) e serviços do sistema (`journald`, `udevd`, `snapd`) foram derrubados pelo watchdog. Com 50 espectadores, o teste simples na VM já deu p99 de 1214 ms. | Se a coleta for na VM: 2 vCPUs, `snapd` desligado, carga calibrada (≤ 20 espectadores) e conferir `uptime`/`vmstat` antes de cada rodada. |
| 10 | **`perf stat` e a versão de cgroup não foram exercitados de forma controlada.** | Contadores de contexto via `/proc/PID/status`; o modo cgroups rodou sem erros, mas a versão do cgroup da máquina do Davi não foi registrada. | Registrar `stat -fc %T /sys/fs/cgroup` em cada rodada; usar `perf stat` se disponível. |

## O que o piloto já comprova

- Ambiente sobe e é desfeito automaticamente a cada execução (Nginx, `stress-ng`, cgroups).
- Execução automatizada de ponta a ponta, em ordem sorteada, com CSV sem sobrescrita, **reproduzida em duas máquinas** (container e Linux do Davi).
- O orquestrador protege contra travamentos: cada cliente tem limite de tempo e uma execução que falha é descartada sem parar a rodada.
- Coleta de latência (média, mediana, p95, p99, máx.), vazão, CPU do servidor, context switches, PSI e CPU do computador.
- Análise reproduzível (`analise/analisar.py`) que gera tabela-resumo e gráficos.

## Como reproduzir

```bash
sudo ESPECTADORES=20 bash executar_piloto.sh 3 8
```

O passo a passo completo está no PDF `como_rodar_piloto.pdf` entregue ao grupo.

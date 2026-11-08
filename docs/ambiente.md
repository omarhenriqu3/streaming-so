# Registro do ambiente

## Piloto (rodada 1) — ambiente de desenvolvimento, NÃO é a VM da coleta definitiva

O piloto foi executado em um container Linux na nuvem, só para validar o pipeline antes da coleta na VM do grupo.

| Item | Valor |
| --- | --- |
| Ambiente | Container Linux (cloud), root |
| CPU | Intel Xeon @ 2,10 GHz, **2 vCPUs** |
| Memória | 8 GB |
| Sistema operacional | Ubuntu 24.04.5 LTS |
| Kernel | 6.18.44-fc-v139 |
| cgroups | v1 (controlador `cpu`) |
| Nginx | 1.24.0 |
| stress-ng | 0.17.06 |
| Python | 3.13.16 (pandas 3.0.5, matplotlib 3.11.2) |
| ab | 2.3 (instalado; o piloto usou o cliente Python) |
| perf | não usado (incompatível com o kernel do container); context switches via `/proc/PID/status` |

## Piloto (rodadas 2 e 3) — máquina Linux do Davi

Rodada 3 (48 execuções) e rodada 2 (teste rápido) foram executadas pelo Davi em um computador Linux. **Preencher com os comandos abaixo (pedir ao Davi):**

| Item | Valor |
| --- | --- |
| Ambiente | Linux (instalado direto ou VM: confirmar) |
| CPU | modelo: ______ , **12 CPUs lógicas** (`nproc` = 12) |
| Memória | ______ (`free -h`) |
| Sistema operacional | ______ (`cat /etc/os-release`) |
| Kernel | **7.0.0-38-generic** |
| cgroups | ______ (`stat -fc %T /sys/fs/cgroup`) |
| Nginx / stress-ng / Python | ______ |
| Condições | 20 espectadores, 8 s por execução, 3 repetições, semente 1792270469 |

## Tentativa na VM do Omar (VirtualBox) — instável

| Item | Valor |
| --- | --- |
| VM | Ubuntu (LVM, 12 GB de disco), **4 vCPUs**, 2,6 GB de RAM |
| cgroups | v2 |
| Python | 3.14 |
| Resultado | O teste isolado (sem isolamento, n=0) rodou: com 50 espectadores p99 = 1214 ms e 140 req/s; com 20 espectadores p99 = 62 ms e 91 req/s. As rodadas completas travaram por esperas de E/S na VM (ver problema 9 em `docs/relatorio_piloto.md`). Nenhum dado desta VM entrou no piloto. |

## Coleta definitiva — preencher na máquina escolhida pelo grupo

Preencher antes da coleta definitiva (e repetir a tabela de condições a cada rodada).

| Item | Valor |
| --- | --- |
| Host (notebook) / CPU / RAM / disco | |
| VirtualBox (versão) | |
| VM: vCPUs / RAM | |
| Distribuição e versão | |
| Kernel | |
| cgroups (v1 ou v2: `stat -fc %T /sys/fs/cgroup`) | |
| Nginx / stress-ng / Python | |

| Condição | Rodada 1 | Rodada 2 | Rodada 3 |
| --- | --- | --- | --- |
| Data e hora | | | |
| Notebook na tomada (sim/não) | | | |
| Responsável | | | |
| Uso de swap na VM (`free -m`) | | | |

# Como rodar o experimento (piloto e mitigação adaptativa)

Roteiro para executar o experimento em uma máquina Linux (Ubuntu/Debian ou derivados), com `sudo` e internet.
Não funciona no Windows nem no macOS.

O script repete, em **5 modos** (sem isolamento, afinidade, cgroups, prioridade e **adaptativo**) × **4 níveis** de
contenção (0, N/2, N e 2N processos do `stress-ng`, onde N é o número de CPUs lógicas), e gera tabelas e gráficos.
No modo adaptativo, `orquestrador/controlador.py` mede a espera do Nginx na fila de execução e limita a CPU do
`stress-ng` quando ela sobe, relaxando o limite quando ela cai (ver `README.md`, seção "Mitigação adaptativa").

**Antes de começar:** notebook na tomada, modo de desempenho, navegador e demais programas fechados, e não usar o
computador durante as execuções (o experimento mede CPU).

## 1. Obter o projeto

Por Git (recomendado, sempre atualizado):

```bash
git clone https://github.com/omarhenriqu3/streaming-so.git
cd streaming-so
```

Ou pelo zip:

```bash
sudo apt update && sudo apt install -y unzip
unzip streaming-so.zip        # se veio do GitHub, o nome pode ser streaming-so-main.zip
cd streaming-so
ls orquestrador workloads
```

Está certo se `orquestrador` mostra `controlador.py` e `run_experimento.py`, e `workloads` mostra `fila_cpu.bt`.
Se faltar `controlador.py`, o zip é uma versão antiga: baixe o atual.

Dê acesso de leitura ao Nginx (necessário se o projeto estiver na pasta pessoal):

```bash
chmod o+x ~
```

## 2. Registrar a máquina

Copie a saída e anote em `docs/ambiente.md`:

```bash
cat /etc/os-release | head -3
uname -r
nproc
lscpu | grep -E "Model name|^CPU\(s\)"
free -h | head -2
df -h / | tail -1
stat -fc %T /sys/fs/cgroup        # cgroup2fs = cgroups v2, tmpfs = v1
cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor
python3 --version
nginx -v 2>&1
stress-ng --version | head -1
ls /sys/kernel/sched_ext          # existe = kernel com suporte a sched_ext
```

Governador de CPU em desempenho (opcional, melhora a repetibilidade):

```bash
sudo apt install -y linux-tools-common linux-tools-$(uname -r)
sudo cpupower frequency-set -g performance
```

## 2b. Confinar o experimento a poucas CPUs (recomendado)

No piloto (12 CPUs livres) a contenção quase não afetou o P99: o escalonador sempre achava uma CPU ociosa.
Para a contenção realmente disputar CPU, o experimento passa a rodar só nas CPUs 0 a 3 (`CPUS=4`): Nginx,
cliente e `stress-ng` ficam nelas, e o orquestrador e o monitor ficam nas outras. Os níveis passam a ser
proporcionais a 4: 0, 2, 4 e 8 processos. O governador de frequência é colocado em `performance` durante a
rodada e restaurado ao final (`--governador nenhum` desliga isso).

Use `CPUS=4` (ou `--cpus 4`) em todos os comandos dos passos seguintes.

## 3. Teste rápido (cerca de 3 minutos)

2 níveis (0 e 8), 1 repetição, 6 s por execução, nos 5 modos (10 execuções):

```bash
sudo CPUS=4 ESPECTADORES=20 NIVEIS="0 8" bash executar_piloto.sh 1 6
```

Aparecem linhas como `[ 3/10] adaptativo n=8 rep=1 p99=9.5 ms thr=97.8 (7s)`.

- **Certo:** `thr=` perto de 95–98 e `p99` de poucos ms (dezenas no máximo) nas 10 execuções.
- **Errado:** `nan` ou `thr=0.0` (ver "Se der problema").
- `thr` bem abaixo de 90: use `ESPECTADORES=10`. Computador forte com p99 < 5 ms em todos: pode usar `ESPECTADORES=30`.

## 4. Calibrar o controlador (cerca de 2 minutos)

Os limiares de espera dependem da máquina. Rode em **modo observação** (só registra, não altera nada):

```bash
sudo python3 orquestrador/run_experimento.py --rodada 50 --repeticoes 1 \
  --duracao 10 --espectadores 20 --modos adaptativo \
  --cpus 4 --niveis 0 2 4 8 --ctl-observar
python3 analise/resumo_controlador.py resultados/brutos/rodada50_*.csv
```

A tabela mostra a mediana e o p90 da espera do Nginx na fila (fração do tempo) por nível. Regra:

- `ALTO`: valor entre a mediana do nível 0 e a mediana do nível 4 (cerca da metade);
- `BAIXO`: cerca de um quarto do `ALTO`, acima da mediana do nível 0.

Os padrões do código (`ALTO` = 0,02 e `BAIXO` = 0,005) vieram de uma máquina de 2 CPUs. Se o nível 0 e o nível 4 tiverem
a mesma espera, a contenção não está chegando ao Nginx: investigar antes de seguir.

## 5. Rodada piloto completa (cerca de 15 minutos)

5 modos × 4 níveis × 3 repetições = 60 execuções:

```bash
sudo CPUS=4 ESPECTADORES=20 CTL_ALTO=0.02 CTL_BAIXO=0.005 bash executar_piloto.sh 3 8
```

Sem calibração, omita `CTL_ALTO` e `CTL_BAIXO`. No fim aparece `pronto: resultados/brutos/ e analise/saida/`.
Execuções travadas são descartadas sozinhas após cerca de 40 s. Os resultados nunca sobrescrevem rodadas anteriores.

## 6. Opcional: medir a espera com eBPF

O controlador usa `/proc/PID/schedstat` e não depende do eBPF. O `bpftrace` (`workloads/fila_cpu.bt`) mede a mesma
espera por dentro do kernel, para confirmar o resultado e medir a sobrecarga.

```bash
sudo apt install -y bpftrace linux-headers-$(uname -r)
bpftrace --version
sudo bpftrace -e 'BEGIN { printf("ebpf ok\n"); exit(); }'
```

Se funcionar, uma execução com o monitor ligado:

```bash
sudo python3 orquestrador/run_experimento.py --rodada 60 --repeticoes 1 \
  --duracao 10 --espectadores 20 --cpus 4 --modos adaptativo --niveis 4 --ebpf
head -5 resultados/brutos/controlador/r60_001_ebpf.csv
```

O arquivo deve ter o cabeçalho `t_ms,espera_total_ns,n,espera_max_ns` e linhas a cada 200 ms.
**Nota:** `fila_cpu.bt` foi escrito mas ainda não foi testado em uma máquina com eBPF.

`sched_ext`: o kernel suporta (`ls /sys/kernel/sched_ext`), mas ainda não há modo `sched_ext` no orquestrador.
Verificar se há pacote: `apt-cache search scx`.

## 7. Enviar os resultados

```bash
zip -r resultados_piloto.zip resultados analise/saida
```

Junto: a saída do passo 2, a tabela do passo 4 e a tabela do fim do passo 5.

## Se der problema

| Sintoma | O que fazer |
|---|---|
| `Permission denied` | Faltou o `sudo`, ou rode `chmod o+x ~` (passo 1). |
| `thr=0.0` e `p99=nan` em todas | Nginx sem acesso aos vídeos: `sudo chmod -R o+rX workloads/video` e `tail -5 /tmp/so_run/error.log`. |
| Falha ao instalar pacotes | Sem internet. Em Fedora/Arch instale `nginx`, `stress-ng`, `python3-pandas` e `python3-matplotlib` manualmente. |
| Erro em `cpu.max` ou `cgroup.subtree_control` | Copie a mensagem inteira e o resultado de `stat -fc %T /sys/fs/cgroup`. O caminho cgroup v2 ainda não foi exercitado em máquina real. |
| `rodada ... já existe` | Rode o script de novo: ele escolhe o próximo número. |
| No modo adaptativo `ctl_acoes` é sempre 0 com contenção alta | Limiar alto demais: refaça o passo 4 e use `CTL_ALTO` menor. |
| Computador lento ou trava | Reinicie, feche outros programas, tente `ESPECTADORES=10`. |
| Sem linhas novas por mais de 2 min | Em outro terminal, `uptime`: carga acima de 10 = computador sufocado; reinicie e repita. |

## Limpeza

Se o script foi interrompido (Ctrl+C):

```bash
sudo pkill stress-ng; sudo pkill -f "nginx -c /tmp/so_run"
sudo rmdir /sys/fs/cgroup/so_servidor /sys/fs/cgroup/so_carga 2>/dev/null
sudo rmdir /sys/fs/cgroup/cpu/so_servidor /sys/fs/cgroup/cpu/so_carga 2>/dev/null
sudo rm -rf /tmp/so_run
```

## Coleta definitiva

Depois de validar tudo: `sudo CPUS=4 ESPECTADORES=20 CTL_ALTO=... CTL_BAIXO=... bash executar_piloto.sh 10 30`
(10 repetições, 30 s; cerca de 2 horas). Combinar antes com a dupla.

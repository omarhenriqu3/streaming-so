#!/usr/bin/env python3
"""Orquestrador do experimento "Streaming sob contenção de recursos".

Para cada (modo de isolamento x nível de contenção x repetição), em ordem sorteada:
  1. inicia o Nginx (1 worker) já com o isolamento do modo aplicado;
  2. inicia o stress-ng com N processos (contenção);
  3. aguarda o warm-up e lê os contadores do SO (PSI, context switches, CPU);
  4. roda o cliente sintético por `--duracao` segundos;
  5. lê os contadores de novo, calcula as métricas e grava uma linha no CSV;
  6. encerra tudo (cooldown).

Uso (como root, pois usa cgroups, nice negativo e sched_setaffinity):
    sudo python3 orquestrador/run_experimento.py --rodada 1 --repeticoes 3 --duracao 8
"""
import argparse
import csv
import datetime as dt
import gzip
import json
import os
import pathlib
import random
import shutil
import signal
import statistics
import subprocess
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from controlador import Controlador  # noqa: E402

RAIZ = pathlib.Path(__file__).resolve().parent.parent
MODOS = ["sem_isolamento", "affinity", "cgroup", "prioridade", "adaptativo"]
RUNDIR = pathlib.Path("/tmp/so_run")
PORTA = 8080

COLUNAS = [
    "rodada", "run_id", "ordem", "modo", "nivel_contencao", "rep", "inicio_iso",
    "duracao_s", "n_req", "n_falhas", "thr_req_s", "thr_MBps",
    "lat_media_ms", "lat_mediana_ms", "lat_p95_ms", "lat_p99_ms", "lat_max_ms",
    "reb_20ms", "reb_50ms", "reb_100ms",
    "cpu_servidor_pct", "ctx_vol", "ctx_invol", "psi_some_us_por_s", "cpu_host_pct",
    "wait_nginx_ms_por_s", "cpu_carga_cpus", "ctl_acoes", "ctl_reacao_s", "ctl_passo_final",
    "loadavg1", "descartada", "obs",
]


# ---------------------------------------------------------------- cgroups (v1 ou v2)
class Cgroups:
    """Cria dois grupos (servidor e carga) com pesos de CPU diferentes."""

    def __init__(self):
        v2 = pathlib.Path("/sys/fs/cgroup/cgroup.controllers")
        if v2.exists() and "cpu" in v2.read_text().split():
            self.versao, self.base = 2, pathlib.Path("/sys/fs/cgroup")
        else:
            self.versao, self.base = 1, pathlib.Path("/sys/fs/cgroup/cpu")
        self.grupos = {}

    def criar(self, nome, peso_v1, peso_v2):
        d = self.base / nome
        d.mkdir(exist_ok=True)
        if self.versao == 1:
            (d / "cpu.shares").write_text(str(peso_v1))
        else:
            (self.base / "cgroup.subtree_control").write_text("+cpu")
            (d / "cpu.weight").write_text(str(peso_v2))
        self.grupos[nome] = d
        return d

    def definir_peso(self, nome, peso_v2):
        d = self.grupos[nome]
        if self.versao == 1:
            (d / "cpu.shares").write_text(str(max(2, int(peso_v2 * 10.24))))
        else:
            (d / "cpu.weight").write_text(str(peso_v2))

    def definir_teto(self, nome, cpus):
        """Teto de CPU do grupo, em número de CPUs (None = sem teto)."""
        d, periodo = self.grupos[nome], 100000
        if self.versao == 1:
            (d / "cpu.cfs_period_us").write_text(str(periodo))
            (d / "cpu.cfs_quota_us").write_text("-1" if cpus is None else str(max(1000, int(cpus * periodo))))
        else:
            quota = "max" if cpus is None else str(max(1000, int(cpus * periodo)))
            (d / "cpu.max").write_text(f"{quota} {periodo}")

    def entrar(self, nome):
        """Função para preexec_fn: coloca o processo filho no grupo."""
        arq = "tasks" if self.versao == 1 else "cgroup.procs"
        caminho = self.grupos[nome] / arq
        return lambda: caminho.write_text(str(os.getpid()))

    def limpar(self):
        for d in self.grupos.values():
            try:
                d.rmdir()
            except OSError:
                pass
        self.grupos = {}


# ---------------------------------------------------------------- leitura de contadores
def psi_cpu_total_us():
    for linha in pathlib.Path("/proc/pressure/cpu").read_text().splitlines():
        if linha.startswith("some"):
            return int(linha.split("total=")[1])
    return 0


def ctx(pid):
    v = i = 0
    for linha in pathlib.Path(f"/proc/{pid}/status").read_text().splitlines():
        if linha.startswith("voluntary_ctxt_switches"):
            v = int(linha.split()[1])
        elif linha.startswith("nonvoluntary_ctxt_switches"):
            i = int(linha.split()[1])
    return v, i


def cpu_ticks(pid):
    campos = pathlib.Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
    return int(campos[11]) + int(campos[12])  # utime + stime


def run_delay_ns(pid):
    """Espera acumulada na fila de execução (ns): 2º campo de /proc/PID/schedstat."""
    return int(pathlib.Path(f"/proc/{pid}/schedstat").read_text().split()[1])


def ticks_grupo(pgid):
    """Soma utime+stime (ticks) de todos os processos do grupo (a carga do stress-ng)."""
    total = 0
    for d in pathlib.Path("/proc").iterdir():
        if not d.name.isdigit():
            continue
        try:
            c = (d / "stat").read_text().rsplit(")", 1)[1].split()
            if int(c[2]) == pgid:
                total += int(c[11]) + int(c[12])
        except (OSError, IndexError):
            pass
    return total


def cpu_host():
    c = list(map(int, pathlib.Path("/proc/stat").read_text().splitlines()[0].split()[1:]))
    ocioso = c[3] + c[4]
    return sum(c), ocioso


# ---------------------------------------------------------------- controle de processos
def pid_worker():
    mestre = int((RUNDIR / "nginx.pid").read_text())
    filhos = subprocess.run(["pgrep", "-P", str(mestre)], capture_output=True, text=True).stdout.split()
    return mestre, int(filhos[0])


def iniciar_nginx(preexec):
    for p in ("tmp_body", "tmp_proxy", "tmp_fcgi", "tmp_uwsgi", "tmp_scgi"):
        (RUNDIR / p).mkdir(exist_ok=True)
    conf = (RAIZ / "configs/nginx.conf.tpl").read_text()
    conf = (conf.replace("@RUNDIR@", str(RUNDIR)).replace("@PORTA@", str(PORTA))
            .replace("@VIDEODIR@", str(RAIZ / "workloads/video")))
    (RUNDIR / "nginx.conf").write_text(conf)
    subprocess.run(["nginx", "-c", str(RUNDIR / "nginx.conf")], preexec_fn=preexec, check=True)
    for _ in range(50):
        if (RUNDIR / "nginx.pid").exists():
            try:
                pid_worker()
                return
            except Exception:
                pass
        time.sleep(0.1)
    raise RuntimeError("nginx não subiu")


def parar_nginx():
    pidf = RUNDIR / "nginx.pid"
    if pidf.exists():
        try:
            os.kill(int(pidf.read_text()), signal.SIGTERM)
        except ProcessLookupError:
            pass
        for _ in range(50):
            if not pidf.exists():
                break
            time.sleep(0.1)
    subprocess.run(["pkill", "-9", "-f", "nginx -c " + str(RUNDIR)], capture_output=True)
    pidf.unlink(missing_ok=True)


def iniciar_stress(n, preexec, duracao):
    if n == 0:
        return None
    return subprocess.Popen(["stress-ng", "--cpu", str(n), "-q", "--timeout", f"{int(duracao)}s"],
                            preexec_fn=preexec, start_new_session=True,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def parar_stress(p):
    if p is None:
        return
    try:
        os.killpg(os.getpgid(p.pid), signal.SIGKILL)
    except ProcessLookupError:
        pass
    p.wait()


# ---------------------------------------------------------------- uma execução
def executar(modo, nivel, args, cg, ncpu, run_id):
    pre_srv = pre_carga = None
    if modo == "affinity" and ncpu > 1:
        outros = set(range(1, ncpu))
        pre_srv = lambda: os.sched_setaffinity(0, {0})
        pre_carga = lambda: os.sched_setaffinity(0, outros)
    elif modo == "cgroup":
        cg.criar("so_servidor", 4096, 400)
        cg.criar("so_carga", 128, 10)
        pre_srv, pre_carga = cg.entrar("so_servidor"), cg.entrar("so_carga")
    elif modo == "prioridade":
        pre_srv = lambda: os.nice(-15)
    elif modo == "adaptativo":
        cg.criar("so_servidor", 1024, 100)   # começa neutro: mesmo peso, sem teto
        cg.criar("so_carga", 1024, 100)
        pre_srv, pre_carga = cg.entrar("so_servidor"), cg.entrar("so_carga")

    stress = ctl = ebpf = None
    try:
        iniciar_nginx(pre_srv)
        mestre, worker = pid_worker()
        stress = iniciar_stress(nivel, pre_carga, args.warmup + args.duracao + 30)
        if modo == "adaptativo":
            (RAIZ / "resultados/brutos/controlador").mkdir(parents=True, exist_ok=True)
            ctl = Controlador(cg, worker, ncpu, RAIZ / f"resultados/brutos/controlador/{run_id}.csv",
                              alto=args.ctl_alto, baixo=args.ctl_baixo, observar=args.ctl_observar)
            ctl.start()
        if args.ebpf:
            (RAIZ / "resultados/brutos/controlador").mkdir(parents=True, exist_ok=True)
            ebpf_out = open(RAIZ / f"resultados/brutos/controlador/{run_id}_ebpf.csv", "w")
            ebpf = subprocess.Popen(["bpftrace", str(RAIZ / "workloads/fila_cpu.bt"), str(worker)],
                                    stdout=ebpf_out, stderr=subprocess.DEVNULL)
        time.sleep(args.warmup)

        v0, i0 = ctx(worker)
        t_cpu0 = cpu_ticks(worker)
        rd0 = run_delay_ns(worker)
        carga0 = ticks_grupo(os.getpgid(stress.pid)) if stress else 0
        psi0 = psi_cpu_total_us()
        h0 = cpu_host()
        w0 = time.perf_counter()

        saida = RUNDIR / "cliente.json"
        subprocess.run([sys.executable, "-I", str(RAIZ / "workloads/cliente_streaming.py"),
                        "--porta", str(PORTA), "--espectadores", str(args.espectadores),
                        "--intervalo", str(args.intervalo), "--duracao", str(args.duracao),
                        "--saida", str(saida)], check=True, timeout=args.duracao + 30)

        w1 = time.perf_counter()
        v1, i1 = ctx(worker)
        t_cpu1 = cpu_ticks(worker)
        rd1 = run_delay_ns(worker)
        carga1 = ticks_grupo(os.getpgid(stress.pid)) if stress else 0
        psi1 = psi_cpu_total_us()
        h1 = cpu_host()
        dados = json.loads(saida.read_text())
        ctl_acoes = ctl.acoes if ctl else ""
        ctl_reacao = round(ctl.t_primeira_acao, 3) if ctl and ctl.t_primeira_acao is not None else ""
        ctl_passo = ctl.passo if ctl else ""
    finally:
        if ctl:
            ctl.encerrar()
        if ebpf:
            ebpf.terminate()
        parar_stress(stress)
        parar_nginx()
        cg.limpar()

    dur = w1 - w0
    ok = [a for a in dados["amostras"] if a["ok"]]
    lat = sorted(a["lat_s"] * 1000 for a in ok)
    n = len(lat)

    def pct(p):
        return lat[min(n - 1, int(p * n))] if n else float("nan")

    clk = os.sysconf("SC_CLK_TCK")
    tot, oc = h1[0] - h0[0], h1[1] - h0[1]
    linha = {
        "duracao_s": round(dur, 3), "n_req": n, "n_falhas": len(dados["amostras"]) - n,
        "thr_req_s": round(n / dur, 2), "thr_MBps": round(sum(a["bytes"] for a in ok) / dur / 1e6, 3),
        "lat_media_ms": round(statistics.fmean(lat), 3) if n else None,
        "lat_mediana_ms": round(statistics.median(lat), 3) if n else None,
        "lat_p95_ms": round(pct(0.95), 3), "lat_p99_ms": round(pct(0.99), 3),
        "lat_max_ms": round(lat[-1], 3) if n else None,
        "reb_20ms": round(sum(x > 20 for x in lat) / n, 5) if n else None,
        "reb_50ms": round(sum(x > 50 for x in lat) / n, 5) if n else None,
        "reb_100ms": round(sum(x > 100 for x in lat) / n, 5) if n else None,
        "cpu_servidor_pct": round(100 * (t_cpu1 - t_cpu0) / clk / dur, 2),
        "ctx_vol": v1 - v0, "ctx_invol": i1 - i0,
        "psi_some_us_por_s": round((psi1 - psi0) / dur, 1),
        "cpu_host_pct": round(100 * (tot - oc) / tot, 2) if tot else None,
        "wait_nginx_ms_por_s": round((rd1 - rd0) / 1e6 / dur, 3),
        "cpu_carga_cpus": round((carga1 - carga0) / clk / dur, 3),
        "ctl_acoes": ctl_acoes, "ctl_reacao_s": ctl_reacao, "ctl_passo_final": ctl_passo,
        "loadavg1": os.getloadavg()[0],
    }
    return linha, lat


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rodada", type=int, default=1)
    ap.add_argument("--repeticoes", type=int, default=3)
    ap.add_argument("--duracao", type=float, default=8.0)
    ap.add_argument("--warmup", type=float, default=2.0)
    ap.add_argument("--cooldown", type=float, default=2.0)
    ap.add_argument("--espectadores", type=int, default=30)
    ap.add_argument("--intervalo", type=float, default=0.25)
    ap.add_argument("--semente", type=int, default=None)
    ap.add_argument("--modos", nargs="*", default=MODOS)
    ap.add_argument("--niveis", nargs="*", type=int, default=None,
                    help="processos do stress-ng; padrão: 0, N/2, N, 2N (N = CPUs lógicas)")
    ap.add_argument("--ctl-alto", type=float, default=0.02, help="limiar de espera (fração do tempo) para agir")
    ap.add_argument("--ctl-baixo", type=float, default=0.005, help="limiar de espera para relaxar")
    ap.add_argument("--ctl-observar", action="store_true", help="controlador só registra, não age")
    ap.add_argument("--ebpf", action="store_true", help="grava também a espera medida pelo bpftrace")
    args = ap.parse_args()
    if args.niveis is None:
        n = os.cpu_count()
        args.niveis = sorted({0, max(1, n // 2), n, 2 * n})

    if os.geteuid() != 0:
        sys.exit("execute como root (cgroups, nice negativo e affinity)")
    RUNDIR.mkdir(exist_ok=True)
    ncpu = os.cpu_count()
    semente = args.semente if args.semente is not None else int(time.time())
    rng = random.Random(semente)

    plano = [(m, n, r) for m in args.modos for n in args.niveis for r in range(1, args.repeticoes + 1)]
    rng.shuffle(plano)

    pasta = RAIZ / "resultados/brutos"
    (pasta / "amostras").mkdir(parents=True, exist_ok=True)
    data = dt.date.today().isoformat()
    csv_path = pasta / f"rodada{args.rodada}_{data}.csv"
    if csv_path.exists():
        sys.exit(f"{csv_path} já existe (nunca sobrescrever): use outra --rodada")
    (pasta / f"rodada{args.rodada}_{data}_meta.json").write_text(json.dumps(
        {"semente": semente, "ncpu": ncpu, "args": vars(args), "kernel": os.uname().release}, indent=2))

    cg = Cgroups()
    print(f"{len(plano)} execuções | ncpu={ncpu} | cgroup v{cg.versao} | semente={semente}", flush=True)
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUNAS)
        w.writeheader()
        for ordem, (modo, nivel, rep) in enumerate(plano, 1):
            run_id = f"r{args.rodada}_{ordem:03d}"
            inicio = dt.datetime.now().isoformat(timespec="seconds")
            obs = ""
            print(f"  -> [{ordem:3d}/{len(plano)}] iniciando {modo} n={nivel} rep={rep} ...", flush=True)
            t_ini = time.time()
            try:
                linha, lat = executar(modo, nivel, args, cg, ncpu, run_id)
                desc = "nao"
                if linha["n_falhas"] > 0 or linha["n_req"] == 0:
                    desc, obs = "sim", "falhas no cliente"
                with gzip.open(pasta / "amostras" / f"{run_id}.csv.gz", "wt") as g:
                    g.write("lat_ms\n" + "\n".join(f"{x:.4f}" for x in lat))
            except Exception as e:  # execução inválida: registra e segue
                linha, desc, obs = {}, "sim", f"erro: {e}"
            linha.update(rodada=args.rodada, run_id=run_id, ordem=ordem, modo=modo,
                         nivel_contencao=nivel, rep=rep, inicio_iso=inicio, descartada=desc, obs=obs)
            w.writerow(linha)
            f.flush()
            print(f"[{ordem:3d}/{len(plano)}] {modo:14s} n={nivel} rep={rep} "
                  f"p99={linha.get('lat_p99_ms')} ms thr={linha.get('thr_req_s')} "
                  f"({time.time() - t_ini:.0f}s) {obs}", flush=True)
            time.sleep(args.cooldown)
    print("rodada concluída:", csv_path)


if __name__ == "__main__":
    main()

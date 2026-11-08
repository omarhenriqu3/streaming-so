"""Controlador de mitigação adaptativa (laço fechado).

Ciclo a cada `periodo` segundos:
  medir   -> espera do worker do Nginx na fila de execução (run_delay de /proc/PID/schedstat);
  decidir -> sinal acima de `alto` por `n_alto` janelas seguidas: aumenta a proteção (um passo);
             sinal abaixo de `baixo` por `n_baixo` janelas seguidas: relaxa (um passo);
  agir    -> ajusta cpu.weight do servidor e o teto (cpu.max) do grupo que gera a carga;
  medir   -> volta ao início.

Só mexe nos dois grupos criados pelo experimento (so_servidor e so_carga).
Modo `observar=True`: registra a decisão sugerida, mas não altera nada.
Cada janela é gravada em CSV (t_s, sinal, passo, acao) para o gráfico da linha do tempo.
"""
import pathlib
import threading
import time


def run_delay_ns(pid):
    """Tempo acumulado que o processo esperou na fila (2º campo de /proc/PID/schedstat)."""
    return int(pathlib.Path(f"/proc/{pid}/schedstat").read_text().split()[1])


class Controlador(threading.Thread):
    def __init__(self, cg, pid_servidor, ncpu, log_csv, periodo=0.2, alto=0.02, baixo=0.005,
                 n_alto=2, n_baixo=10, intervalo_min=0.4, observar=False):
        super().__init__(daemon=True)
        self.cg, self.pid, self.ncpu, self.log_csv = cg, pid_servidor, ncpu, log_csv
        self.periodo, self.alto, self.baixo = periodo, alto, baixo
        self.n_alto, self.n_baixo, self.intervalo_min = n_alto, n_baixo, intervalo_min
        self.observar = observar
        # (cpu.weight do servidor, teto da carga como fração de TODAS as CPUs; None = sem teto)
        self.passos = [(100, None), (400, 0.50), (1000, 0.25), (1000, 0.10)]
        self.passo = 0
        self.acoes = 0
        self.t_primeira_acao = None
        self.parar = threading.Event()
        self.t0 = None

    def aplicar(self, passo):
        peso, teto = self.passos[passo]
        self.cg.definir_peso("so_servidor", peso)
        self.cg.definir_teto("so_carga", None if teto is None else teto * self.ncpu)

    def run(self):
        self.t0 = time.perf_counter()
        ult_acao = -1e9
        cont_alto = cont_baixo = 0
        anterior = run_delay_ns(self.pid)
        t_ant = time.perf_counter()
        with open(self.log_csv, "w") as f:
            f.write("t_s,sinal,passo,acao\n")
            while not self.parar.wait(self.periodo):
                try:
                    atual = run_delay_ns(self.pid)
                except (FileNotFoundError, ProcessLookupError):
                    break
                agora = time.perf_counter()
                sinal = (atual - anterior) / 1e9 / (agora - t_ant)  # fração do tempo esperando na fila
                anterior, t_ant = atual, agora
                cont_alto = cont_alto + 1 if sinal > self.alto else 0
                cont_baixo = cont_baixo + 1 if sinal < self.baixo else 0
                acao = "-"
                t = agora - self.t0
                if t - ult_acao >= self.intervalo_min:
                    novo = self.passo
                    if cont_alto >= self.n_alto and self.passo < len(self.passos) - 1:
                        novo, acao = self.passo + 1, "sobe"
                    elif cont_baixo >= self.n_baixo and self.passo > 0:
                        novo, acao = self.passo - 1, "relaxa"
                    if novo != self.passo:
                        if self.observar:
                            acao += "(simulado)"
                        else:
                            self.passo = novo
                            self.aplicar(novo)
                        self.acoes += 1
                        if self.t_primeira_acao is None:
                            self.t_primeira_acao = t
                        ult_acao, cont_alto, cont_baixo = t, 0, 0
                f.write(f"{t:.3f},{sinal:.5f},{self.passo},{acao}\n")
                f.flush()

    def encerrar(self):
        self.parar.set()
        self.join(timeout=2)

#!/usr/bin/env python3
"""Análise preliminar: lê os CSVs brutos de uma rodada, gera a tabela-resumo e os gráficos.

Uso:
    python3 analise/analisar.py --rodada 1
Saídas (em analise/saida/): resumo_rodadaN.csv, fig1_latencia_vs_contencao.png,
fig2_indicadores_so.png
"""
import argparse
import glob
import pathlib

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

RAIZ = pathlib.Path(__file__).resolve().parent.parent
MODOS = ["sem_isolamento", "affinity", "cgroup", "prioridade", "adaptativo"]
ROTULO = {"sem_isolamento": "Sem isolamento", "affinity": "CPU affinity",
          "cgroup": "cgroups", "prioridade": "Prioridade (nice)", "adaptativo": "Adaptativo (eBPF)"}
# slots categóricos 1-4 da paleta validada (azul, laranja, água, amarelo), ordem fixa
COR = {"sem_isolamento": "#2a78d6", "affinity": "#eb6834", "cgroup": "#1baf7a", "prioridade": "#eda100", "adaptativo": "#8f4fd6"}
SUPERFICIE, TXT1, TXT2, GRADE = "#fcfcfb", "#0b0b0b", "#52514e", "#e6e5e1"


def carregar(rodada):
    arqs = sorted(glob.glob(str(RAIZ / f"resultados/brutos/rodada{rodada}_*.csv")))
    if not arqs:
        raise SystemExit("nenhum CSV encontrado")
    df = pd.concat(pd.read_csv(a) for a in arqs)
    return df


def estilo(ax):
    ax.set_facecolor(SUPERFICIE)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRADE)
    ax.tick_params(colors=TXT2, labelsize=10, length=0)
    ax.grid(axis="y", color=GRADE, linewidth=0.8)
    ax.set_axisbelow(True)


def rotulos_diretos(ax, finais, xfim):
    """Rótulos no fim das linhas, afastados para não colidirem."""
    y0, y1 = ax.get_ylim()
    sep = 0.07 * (y1 - y0)
    ordem = sorted(finais.items(), key=lambda kv: kv[1])
    pos, ult = {}, None
    for m, y in ordem:
        pos[m] = y if ult is None or y - ult >= sep else ult + sep
        ult = pos[m]
    for m, y in pos.items():
        ax.annotate(ROTULO[m], (xfim, finais[m]), xytext=(xfim + 0.12, y), color=TXT1,
                    fontsize=10, va="center", annotation_clip=False,
                    arrowprops=dict(arrowstyle="-", color=COR[m], lw=0.8, shrinkA=0, shrinkB=2))


def painel(ax, df, col, titulo, ylab):
    niveis = sorted(df.nivel_contencao.unique())
    xs = {n: i for i, n in enumerate(niveis)}
    finais = {}
    for m in MODOS:
        d = df[df.modo == m]
        if d.empty:
            continue
        media = d.groupby("nivel_contencao")[col].mean()
        ax.scatter([xs[n] for n in d.nivel_contencao], d[col], s=18, color=COR[m], alpha=0.35,
                   linewidths=0, zorder=2)
        ax.plot([xs[n] for n in media.index], media.values, color=COR[m], lw=2, zorder=3,
                marker="o", ms=8, markeredgecolor=SUPERFICIE, markeredgewidth=2)
        finais[m] = media.values[-1]
    ax.set_xticks(range(len(niveis)))
    ax.set_xticklabels([str(n) for n in niveis])
    ax.set_xlabel("Processos concorrentes (stress-ng)", color=TXT2, fontsize=10)
    ax.set_ylabel(ylab, color=TXT2, fontsize=10)
    ax.set_title(titulo, loc="left", color=TXT1, fontsize=12, fontweight="bold")
    ax.set_xlim(-0.2, len(niveis) - 1 + 0.2)
    ax.set_ylim(bottom=0)
    estilo(ax)
    ax.figure.canvas.draw()
    rotulos_diretos(ax, finais, len(niveis) - 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rodada", type=int, default=1)
    a = ap.parse_args()
    df = carregar(a.rodada)
    n_tot = len(df)
    df = df[df.descartada == "nao"].copy()
    df["psi_pct"] = df.psi_some_us_por_s / 1e4  # µs por s -> % do tempo
    print(f"{len(df)} execuções válidas de {n_tot}")
    saida = RAIZ / "analise/saida"
    saida.mkdir(exist_ok=True)

    metricas = ["thr_req_s", "lat_mediana_ms", "lat_p95_ms", "lat_p99_ms", "reb_20ms",
                "cpu_servidor_pct", "ctx_invol", "psi_pct"]
    resumo = df.groupby(["modo", "nivel_contencao"])[metricas].agg(["mean", "std"]).round(3)
    resumo.columns = [f"{c}_{s}" for c, s in resumo.columns]
    resumo["n_exec"] = df.groupby(["modo", "nivel_contencao"]).size()
    resumo.to_csv(saida / f"resumo_rodada{a.rodada}.csv")

    plt.rcParams["font.family"] = "DejaVu Sans"
    fig, axs = plt.subplots(1, 2, figsize=(13, 4.8), facecolor=SUPERFICIE)
    painel(axs[0], df, "lat_p99_ms", "Latência p99 por segmento", "ms")
    painel(axs[1], df, "lat_mediana_ms", "Latência mediana por segmento", "ms")
    fig.suptitle("Piloto: latência do servidor de streaming sob contenção de CPU",
                 x=0.01, ha="left", color=TXT1, fontsize=14, fontweight="bold")
    fig.text(0.01, 0.005, "Linha = média das repetições; pontos = repetições individuais (piloto, n por configuração pequeno).",
             color=TXT2, fontsize=9)
    fig.tight_layout(rect=(0, 0.03, 0.93, 0.94))
    fig.savefig(saida / "fig1_latencia_vs_contencao.png", dpi=170, facecolor=SUPERFICIE)

    fig, axs = plt.subplots(1, 2, figsize=(13, 4.8), facecolor=SUPERFICIE)
    painel(axs[0], df, "ctx_invol", "Context switches involuntários (servidor)", "trocas por execução")
    painel(axs[1], df, "psi_pct", "PSI de CPU (some, sistema inteiro)", "% do tempo com tarefa esperando CPU")
    fig.suptitle("Piloto: indicadores internos do sistema operacional",
                 x=0.01, ha="left", color=TXT1, fontsize=14, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 0.93, 0.94))
    fig.savefig(saida / "fig2_indicadores_so.png", dpi=170, facecolor=SUPERFICIE)
    print(resumo[["lat_mediana_ms_mean", "lat_p99_ms_mean", "thr_req_s_mean", "n_exec"]].to_string())


if __name__ == "__main__":
    main()

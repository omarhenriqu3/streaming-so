#!/usr/bin/env python3
"""Tratamento estatístico e gráficos finais.

Uso:
    python3 analise/estatistica.py --rodadas 5            # piloto
    python3 analise/estatistica.py --rodadas 7 --nome definitiva

Por configuração (modo x nível) e por métrica: mediana, IQR e IC 95% da mediana (bootstrap percentil,
10 000 reamostragens, semente fixa). Comparação de cada modo com "sem_isolamento" no mesmo nível:
Mann-Whitney U bilateral, delta de Cliff (tamanho do efeito) e correção de Holm por família
(métrica x nível). Correlação de Spearman entre a espera do Nginx na fila e o P99.
A unidade de análise é a execução (n = repetições por configuração), nunca as requisições.
Saídas em analise/saida/<nome>/: tabelas (.csv/.tex) e figuras (.png).
"""
import argparse
import glob
import json
import pathlib

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

RAIZ = pathlib.Path(__file__).resolve().parent.parent
MODOS = ["sem_isolamento", "affinity", "cgroup", "prioridade", "adaptativo"]
ROTULO = {"sem_isolamento": "Sem isolamento", "affinity": "Afinidade (taskset)", "cgroup": "cgroups (peso)",
          "prioridade": "Prioridade (nice)", "adaptativo": "Adaptativo (eBPF)"}
COR = {"sem_isolamento": "#2a78d6", "affinity": "#eb6834", "cgroup": "#1baf7a", "prioridade": "#eda100",
       "adaptativo": "#8f4fd6"}
MARC = {"sem_isolamento": "o", "affinity": "s", "cgroup": "^", "prioridade": "D", "adaptativo": "P"}
METRICAS = {
    "lat_p99_ms": "P99 da latência (ms)", "lat_p95_ms": "P95 da latência (ms)",
    "reb_20ms": "Rebuffering (fração > 20 ms)", "thr_req_s": "Vazão (req/s)",
    "wait_nginx_ms_por_s": "Espera do Nginx na fila (ms/s)", "cpu_carga_cpus": "CPU usada pela carga (CPUs)",
}
SUPERFICIE, TXT1, TXT2, GRADE = "#fcfcfb", "#0b0b0b", "#52514e", "#e6e5e1"
B = 10_000
rng = np.random.default_rng(2026)


def carregar(rodadas):
    arqs = []
    for r in rodadas:
        arqs += sorted(glob.glob(str(RAIZ / f"resultados/brutos/rodada{r}_*.csv")))
    if not arqs:
        raise SystemExit("nenhum CSV encontrado")
    d = pd.concat([pd.read_csv(a) for a in arqs], ignore_index=True)
    n0 = len(d)
    d = d[d.descartada != "sim"].copy()
    print(f"{n0} execuções lidas, {n0 - len(d)} descartadas, {len(d)} válidas")
    return d


def ic_mediana(x):
    x = np.asarray(x, float)
    if len(x) < 2:
        return (np.nan, np.nan)
    med = np.median(rng.choice(x, size=(B, len(x)), replace=True), axis=1)
    return tuple(np.percentile(med, [2.5, 97.5]))


def cliff(a, b):
    u = stats.mannwhitneyu(a, b, alternative="two-sided")
    return u.pvalue, 2 * u.statistic / (len(a) * len(b)) - 1


def holm(p):
    p = np.asarray(p, float)
    o = np.argsort(p)
    aj = np.empty_like(p)
    m, corr = len(p), 0.0
    for i, k in enumerate(o):
        corr = max(corr, (m - i) * p[k])
        aj[k] = min(1.0, corr)
    return aj


def estilo(ax):
    ax.set_facecolor(SUPERFICIE)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRADE)
    ax.tick_params(colors=TXT2)
    ax.grid(axis="y", color=GRADE, lw=0.8)
    ax.set_axisbelow(True)


def tabela_resumo(d, saida):
    linhas = []
    for (nivel, modo), g in d.groupby(["nivel_contencao", "modo"]):
        for m in METRICAS:
            x = g[m].dropna()
            if len(x) == 0:
                continue
            lo, hi = ic_mediana(x)
            linhas.append(dict(nivel=nivel, modo=modo, metrica=m, n=len(x), mediana=np.median(x),
                               q1=x.quantile(.25), q3=x.quantile(.75), ic_lo=lo, ic_hi=hi))
    t = pd.DataFrame(linhas)
    t.round(3).to_csv(saida / "tabela_resumo.csv", index=False)
    return t


def latex_resumo(t, saida, metrica="lat_p99_ms", nome="tab_p99.tex", legenda="", rotulo=""):
    niveis = sorted(t.nivel.unique())
    ls = ["\\begin{table}[H]", "\\centering", "\\small", f"\\caption{{{legenda}}}", f"\\label{{{rotulo}}}",
          "\\begin{tabular}{l" + "c" * len(niveis) + "}", "\\toprule",
          "\\textbf{Modo} & " + " & ".join(f"\\textbf{{{n} proc.}}" for n in niveis) + " \\\\", "\\midrule"]
    for m in MODOS:
        cel = []
        for n in niveis:
            r = t[(t.modo == m) & (t.nivel == n) & (t.metrica == metrica)]
            if r.empty:
                cel.append("--")
                continue
            r = r.iloc[0]
            cel.append(f"{r.mediana:.1f} [{r.ic_lo:.1f}; {r.ic_hi:.1f}]")
        ls.append(ROTULO[m] + " & " + " & ".join(cel) + " \\\\")
    ls += ["\\bottomrule", "\\end{tabular}", "\\end{table}"]
    (saida / nome).write_text("\n".join(ls) + "\n", encoding="utf-8")


def testes(d, saida):
    linhas = []
    for m in ["lat_p99_ms", "reb_20ms", "wait_nginx_ms_por_s", "cpu_carga_cpus", "thr_req_s"]:
        for nivel, g in d.groupby("nivel_contencao"):
            ref = g[g.modo == "sem_isolamento"][m].dropna()
            fam = []
            for modo in MODOS[1:]:
                x = g[g.modo == modo][m].dropna()
                if len(ref) < 3 or len(x) < 3 or nivel == 0 and m == "cpu_carga_cpus":
                    continue
                p, dl = cliff(x, ref)
                fam.append(dict(metrica=m, nivel=nivel, modo=modo, n=len(x), n_ref=len(ref),
                                mediana=np.median(x), mediana_ref=np.median(ref), p=p, cliff=dl))
            if fam:
                adj = holm([f["p"] for f in fam])
                for f, a in zip(fam, adj):
                    f["p_holm"] = a
                linhas += fam
    t = pd.DataFrame(linhas)
    t.round(4).to_csv(saida / "testes_vs_sem_isolamento.csv", index=False)
    return t


def correlacao(d, saida):
    out = []
    for nome, g in [("todas", d)] + [(m, d[d.modo == m]) for m in MODOS]:
        g = g[["wait_nginx_ms_por_s", "lat_p99_ms"]].dropna()
        if len(g) < 5:
            continue
        rho, p = stats.spearmanr(g.wait_nginx_ms_por_s, g.lat_p99_ms)
        idx = rng.integers(0, len(g), size=(2000, len(g)))
        bs = [stats.spearmanr(g.wait_nginx_ms_por_s.values[i], g.lat_p99_ms.values[i])[0] for i in idx]
        out.append(dict(grupo=nome, n=len(g), rho=rho, p=p, ic_lo=np.nanpercentile(bs, 2.5),
                        ic_hi=np.nanpercentile(bs, 97.5)))
    t = pd.DataFrame(out)
    t.round(4).to_csv(saida / "correlacao_espera_p99.csv", index=False)
    return t


def fig_linhas(t, metrica, ylabel, arq, saida, log=False, titulo=""):
    fig, ax = plt.subplots(figsize=(7.2, 4.2), facecolor=SUPERFICIE)
    estilo(ax)
    niveis = sorted(t.nivel.unique())
    x = np.arange(len(niveis))
    for m in MODOS:
        r = t[(t.modo == m) & (t.metrica == metrica)].set_index("nivel").reindex(niveis)
        if r.mediana.isna().all():
            continue
        ax.errorbar(x, r.mediana, yerr=[r.mediana - r.ic_lo, r.ic_hi - r.mediana], color=COR[m], marker=MARC[m],
                    ms=6, lw=1.8, capsize=3, label=ROTULO[m])
    ax.set_xticks(x, [str(n) for n in niveis])
    ax.set_xlabel("Contenção (processos do stress-ng)", color=TXT2)
    ax.set_ylabel(ylabel, color=TXT2)
    if log:
        ax.set_yscale("log")
    if titulo:
        ax.set_title(titulo, loc="left", color=TXT1, fontsize=11)
    ax.legend(frameon=False, fontsize=8.5)
    fig.tight_layout()
    fig.savefig(saida / arq, dpi=200)
    plt.close(fig)


def fig_custo(d, nivel, saida):
    g = d[d.nivel_contencao == nivel]
    fig, ax = plt.subplots(figsize=(6.4, 4.4), facecolor=SUPERFICIE)
    estilo(ax)
    for m in MODOS:
        x = g[g.modo == m]
        if x.empty:
            continue
        ax.scatter(x.cpu_carga_cpus, x.lat_p99_ms, color=COR[m], marker=MARC[m], s=34, alpha=.8, label=ROTULO[m])
    ax.set_xlabel("CPU obtida pela carga (CPUs)", color=TXT2)
    ax.set_ylabel("P99 da latência (ms)", color=TXT2)
    ax.set_title(f"Proteção do Nginx × custo para a carga ({nivel} processos)", loc="left", color=TXT1, fontsize=11)
    ax.legend(frameon=False, fontsize=8.5)
    fig.tight_layout()
    fig.savefig(saida / "fig_custo_vs_p99.png", dpi=200)
    plt.close(fig)


def fig_timeline(d, saida):
    cand = d[(d.modo == "adaptativo") & (d.nivel_contencao == d.nivel_contencao.max()) & (d.ctl_acoes > 0)]
    for _, r in cand.iterrows():
        f = RAIZ / f"resultados/brutos/controlador/{r.run_id}.csv"
        if f.exists():
            c = pd.read_csv(f)
            break
    else:
        return
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(7.2, 4.4), sharex=True, facecolor=SUPERFICIE,
                                 gridspec_kw={"height_ratios": [3, 1.3]})
    for a in (a1, a2):
        estilo(a)
    mt = glob.glob(str(RAIZ / f"resultados/brutos/rodada{int(r.rodada)}_*_meta.json"))
    aq = json.load(open(mt[0]))["args"]["warmup"] if mt else 0
    for a in (a1, a2):
        a.axvline(aq, color=GRADE, lw=1.4, ls="--")
    a1.text(aq + 0.08, a1.get_ylim()[1] * 0.92, "cliente começa", color=TXT2, fontsize=8)
    a1.plot(c.t_s, c.sinal * 1000, color=COR["adaptativo"], lw=1.4)
    a1.set_ylabel("Espera do Nginx (ms/s)", color=TXT2)
    a1.set_title(f"Controlador em ação ({r.run_id}, {int(r.nivel_contencao)} processos)", loc="left", color=TXT1,
                 fontsize=11)
    a2.step(c.t_s, c.passo, where="post", color=TXT1, lw=1.6)
    a2.set_ylabel("Degrau", color=TXT2)
    a2.set_xlabel("Tempo desde o início da execução (s)", color=TXT2)
    a2.set_yticks(sorted(c.passo.unique()))
    fig.tight_layout()
    fig.savefig(saida / "fig_timeline_controlador.png", dpi=200)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rodadas", nargs="+", type=int, required=True)
    ap.add_argument("--nome", default=None)
    a = ap.parse_args()
    nome = a.nome or "rodadas_" + "_".join(map(str, a.rodadas))
    saida = RAIZ / "analise/saida" / nome
    saida.mkdir(parents=True, exist_ok=True)
    d = carregar(a.rodadas)
    reps = d.groupby(["modo", "nivel_contencao"]).size()
    print("repetições por configuração: min", reps.min(), "max", reps.max())
    t = tabela_resumo(d, saida)
    latex_resumo(t, saida, "lat_p99_ms", "tab_p99.tex", "P99 da latência (ms): mediana [IC 95\\% bootstrap].", "tab:p99")
    latex_resumo(t, saida, "wait_nginx_ms_por_s", "tab_espera.tex",
                 "Espera do Nginx na fila de execução (ms/s): mediana [IC 95\\%].", "tab:espera")
    latex_resumo(t, saida, "cpu_carga_cpus", "tab_custo.tex",
                 "CPU obtida pela carga do stress-ng (CPUs): mediana [IC 95\\%].", "tab:custo")
    tt = testes(d, saida)
    co = correlacao(d, saida)
    fig_linhas(t, "lat_p99_ms", "P99 da latência (ms)", "fig_p99_vs_contencao.png", saida,
               titulo="P99 vs. contenção (mediana e IC 95%)")
    fig_linhas(t, "wait_nginx_ms_por_s", "Espera na fila (ms/s, escala log)", "fig_espera_vs_contencao.png", saida,
               log=True, titulo="Espera do Nginx na fila vs. contenção")
    fig_linhas(t, "cpu_carga_cpus", "CPU usada pela carga (CPUs)", "fig_custo_carga.png", saida,
               titulo="Custo para a carga concorrente")
    fig_custo(d, d.nivel_contencao.max(), saida)
    fig_timeline(d, saida)
    print(co.round(3).to_string(index=False))
    sig = tt[(tt.metrica == "lat_p99_ms") & (tt.p_holm < 0.05)]
    print("\ncomparações de P99 com p ajustado < 0,05:", len(sig))
    print(sig[["nivel", "modo", "mediana", "mediana_ref", "cliff", "p_holm"]].round(3).to_string(index=False))
    ad = d[(d.modo == "adaptativo") & (d.ctl_acoes > 0)].copy()
    if len(ad):
        w = {int(r): json.load(open(glob.glob(str(RAIZ / f"resultados/brutos/rodada{int(r)}_*_meta.json"))[0]))["args"]["warmup"]
             for r in ad.rodada.unique()}
        ad["reacao_apos_cliente_s"] = ad.ctl_reacao_s - ad.rodada.map(w)
        print("\nreação do controlador após o início do cliente (s): mediana",
              round(ad.reacao_apos_cliente_s.median(), 2), "min", round(ad.reacao_apos_cliente_s.min(), 2),
              "max", round(ad.reacao_apos_cliente_s.max(), 2), "n", len(ad))
    print("saída em", saida)


if __name__ == "__main__":
    main()

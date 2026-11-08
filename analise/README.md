# analise

`analisar.py --rodada N` lê `resultados/brutos/rodadaN_*.csv`, descarta execuções marcadas como falha e gera em `analise/saida/`:

- `resumo_rodadaN.csv`: média e desvio por modo × nível (tabela de apoio aos gráficos);
- `fig1_latencia_vs_contencao.png`: latência p99 e mediana vs. número de processos concorrentes;
- `fig2_indicadores_so.png`: context switches involuntários e PSI de CPU.

Para a coleta definitiva, acrescentar mediana/IQR, testes Mann–Whitney e Kruskal–Wallis e intervalos de confiança por bootstrap.

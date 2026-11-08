# workloads

- `gerar_segmentos.sh`: gera 20 segmentos de 400 KB (bytes aleatórios; o Nginx só entrega bytes, então o custo de CPU é equivalente ao de segmentos reais de vídeo). Os arquivos em `video/` não vão para o Git.
- `cliente_streaming.py`: cliente sintético. Simula N espectadores; cada um pede um segmento a cada `--intervalo` s por uma conexão HTTP persistente e registra a latência até o recebimento completo.
- Servidor: Nginx com 1 worker (`configs/nginx.conf.tpl`), `sendfile off` para que o servidor copie os dados e gaste CPU por requisição.
- Carga concorrente: `stress-ng --cpu N`.

Parâmetros do piloto: 50 espectadores, 0,2 s entre pedidos (≈ 250 req/s, ≈ 100 MB/s).

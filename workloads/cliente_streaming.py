#!/usr/bin/env python3
"""Cliente sintético de streaming.

Simula N espectadores. Cada espectador pede os segmentos em sequência, no ritmo de
reprodução (um segmento a cada `--intervalo` segundos). Para cada segmento registra a
latência até o recebimento completo. Um segmento "atrasado" (rebuffering) é aquele
cuja latência passa de `--prazo` segundos, ou seja, não chegou a tempo de manter a
reprodução contínua.

Saída: um JSON com as amostras brutas (stdout ou --saida).
"""
import argparse
import http.client
import json
import threading
import time


def espectador(porta, n_seg, intervalo, deadline_fim, amostras, trava, ident):
    conn = http.client.HTTPConnection("127.0.0.1", porta, timeout=10)
    i = 0
    proximo = time.perf_counter()
    while time.perf_counter() < deadline_fim:
        nome = f"/seg_{(i % n_seg) + 1:03d}.ts"
        t0 = time.perf_counter()
        try:
            conn.request("GET", nome)
            resp = conn.getresponse()
            corpo = resp.read()
            ok = resp.status == 200
            nbytes = len(corpo)
        except Exception:
            ok, nbytes = False, 0
            conn.close()
            conn = http.client.HTTPConnection("127.0.0.1", porta, timeout=10)
        t1 = time.perf_counter()
        with trava:
            amostras.append({"espectador": ident, "t": t0, "lat_s": t1 - t0, "bytes": nbytes, "ok": ok})
        i += 1
        proximo += intervalo
        espera = proximo - time.perf_counter()
        if espera > 0:
            time.sleep(espera)
        else:
            proximo = time.perf_counter()  # atrasado: não acumula "dívida" de pedidos
    conn.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--porta", type=int, default=8080)
    ap.add_argument("--espectadores", type=int, default=30)
    ap.add_argument("--n-seg", type=int, default=20)
    ap.add_argument("--intervalo", type=float, default=0.25, help="s entre pedidos de um espectador")
    ap.add_argument("--duracao", type=float, default=10.0)
    ap.add_argument("--saida", default="-")
    a = ap.parse_args()

    amostras, trava = [], threading.Lock()
    fim = time.perf_counter() + a.duracao
    ths = [threading.Thread(target=espectador,
                            args=(a.porta, a.n_seg, a.intervalo, fim, amostras, trava, k))
           for k in range(a.espectadores)]
    inicio = time.perf_counter()
    for t in ths:
        t.start()
    for t in ths:
        t.join()
    dur = time.perf_counter() - inicio
    out = {"duracao_s": dur, "amostras": amostras}
    if a.saida == "-":
        print(json.dumps(out))
    else:
        with open(a.saida, "w") as f:
            json.dump(out, f)


if __name__ == "__main__":
    main()

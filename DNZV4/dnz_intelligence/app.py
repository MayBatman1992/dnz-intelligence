"""DNZ Intelligence — aplicação web (v4)

Módulo 1: calibrador de metas (regra explicável, validada por backtest)
Módulo 2: motor de comissionamento configurável
Simulação retrospectiva de cenários, fechamento do mês e evidências.

Cada visitante tem o seu próprio estado (dados enviados e parâmetros), guardado em memória.
Roda com 1 worker (padrão do gunicorn).
"""
import json
import os
import secrets
import threading
import time

from flask import Flask, jsonify, render_template, request, send_from_directory, session

import engine
from calibrador import sugerir_metas_time, _chave
from leitor import ler_arquivo
from simulacao import simular

BASE = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)

_ESTADOS, _LOCK = {}, threading.Lock()
MAX_ESTADOS, TTL = 300, 6 * 3600
_DEMO = {}


def _demo():
    if not _DEMO:
        with open(os.path.join(BASE, "data", "demo_historico.csv"), "rb") as f:
            r = ler_arquivo(f.read(), "demo_historico.csv")
        _DEMO.update(r)
    return _DEMO


def _estado():
    with _LOCK:
        agora = time.time()
        for sid in [k for k, e in _ESTADOS.items() if agora - e["ts"] > TTL]:
            del _ESTADOS[sid]
        if len(_ESTADOS) > MAX_ESTADOS:
            for sid in sorted(_ESTADOS, key=lambda k: _ESTADOS[k]["ts"])[:50]:
                del _ESTADOS[sid]
        sid = session.get("sid")
        if sid not in _ESTADOS:
            sid = secrets.token_hex(8)
            session["sid"] = sid
            _ESTADOS[sid] = {"ts": agora, "vendedores": None, "fonte": "demo", "cfg": engine.config_padrao()}
        e = _ESTADOS[sid]
        e["ts"] = agora
    if e["vendedores"] is None:
        e["vendedores"], e["fonte"] = _demo()["vendedores"], "demo"
    return e


def _periodos(vendedores):
    chaves = sorted({_chave(h) for v in vendedores for h in v["historico"]})
    return chaves


def _rot(chave):
    return f"{(chave - 1) // 12}-{(chave - 1) % 12 + 1:02d}"


def _resumo_estado(e):
    V, chaves = e["vendedores"], _periodos(e["vendedores"])
    ult = chaves[-1]
    prox = ult + 1
    return {
        "fonte": e["fonte"], "demo": e["fonte"] == "demo",
        "n_vendedores": len(V), "n_registros": sum(len(v["historico"]) for v in V),
        "periodo_min": _rot(chaves[0]), "periodo_max": _rot(ult), "n_periodos": len(chaves),
        "ultimo": {"ano": (ult - 1) // 12, "mes": (ult - 1) % 12 + 1},
        "proximo": {"ano": (prox - 1) // 12, "mes": (prox - 1) % 12 + 1},
        "tem_obs": any("obs" in h for v in V for h in v["historico"]),
        "tem_meta_real": any("meta" in h for v in V for h in v["historico"]),
        "vendedores": [{"id": v["id"], "nome": v["nome"], "canal": v["canal"], "senioridade": v["senioridade"],
                        "meses": len(v["historico"])} for v in V],
    }


def _json_body():
    return request.get_json(silent=True) or {}


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/template")
def baixar_template():
    return send_from_directory(os.path.join(BASE, "data"), "template_historico.xlsx", as_attachment=True,
                               download_name="DNZ_template_historico.xlsx")


@app.route("/api/estado")
def api_estado():
    e = _estado()
    return jsonify({**_resumo_estado(e), "config": e["cfg"]})


@app.route("/api/upload", methods=["POST"])
def api_upload():
    e = _estado()
    arq = request.files.get("arquivo")
    if not arq or not arq.filename:
        return jsonify({"status": "erro", "mensagem": "Nenhum arquivo enviado."}), 400
    r = ler_arquivo(arq.read(), arq.filename)
    if r["status"] != "ok":
        return jsonify(r), 400
    e["vendedores"], e["fonte"] = r["vendedores"], arq.filename
    return jsonify({"status": "ok", **_resumo_estado(e)})


@app.route("/api/usar_demo", methods=["POST"])
def api_usar_demo():
    e = _estado()
    e["vendedores"], e["fonte"] = _demo()["vendedores"], "demo"
    return jsonify({"status": "ok", **_resumo_estado(e)})


@app.route("/api/config", methods=["GET", "POST"])
def api_config():
    e = _estado()
    if request.method == "POST":
        cfg, erros = engine.validar_config(_json_body())
        if erros:
            return jsonify({"status": "erro", "mensagem": " | ".join(erros)}), 400
        e["cfg"] = cfg
    return jsonify({"status": "ok", "config": e["cfg"], "tabela": engine.tabela_aceleradores(e["cfg"])})


@app.route("/api/config/reset", methods=["POST"])
def api_config_reset():
    e = _estado()
    e["cfg"] = engine.config_padrao()
    return jsonify({"status": "ok", "config": e["cfg"], "tabela": engine.tabela_aceleradores(e["cfg"])})


@app.route("/api/metas", methods=["POST"])
def api_metas():
    e, b = _estado(), _json_body()
    try:
        mes, ano = int(b.get("mes", 1)), int(b.get("ano", 2026))
        fator = float(b.get("fator_desafio", e["cfg"]["fator_desafio"]))
    except (TypeError, ValueError):
        return jsonify({"status": "erro", "mensagem": "Parâmetros inválidos."}), 400
    ctx, metas = sugerir_metas_time(e["vendedores"], mes, ano, fator, b.get("status_override"))
    return jsonify({"status": "ok", "fatores": {k: round(v, 3) for k, v in ctx["fatores"].items()},
                    "origem_fatores": ctx["origem_fatores"], "linhas_por_status": ctx["n_linhas"],
                    "n_periodos": len(_periodos(e["vendedores"])), "metas": metas})


@app.route("/api/comissao", methods=["POST"])
def api_comissao():
    e, b = _estado(), _json_body()
    try:
        r = engine.calcular_comissao(float(b["mrr"]), float(b["meta"]), b["canal"], b["senioridade"],
                                     int(b.get("meses_contrato") or e["cfg"]["meses_contrato"]), e["cfg"])
        return jsonify({"status": "ok", **r})
    except (KeyError, ValueError, TypeError) as ex:
        return jsonify({"status": "erro", "mensagem": str(ex)}), 400


@app.route("/api/simulacao", methods=["POST"])
def api_simulacao():
    e, b = _estado(), _json_body()
    try:
        mes, ano = int(b["mes"]), int(b["ano"])
        fator = float(b.get("fator_desafio", e["cfg"]["fator_desafio"]))
    except (KeyError, TypeError, ValueError):
        return jsonify({"status": "erro", "mensagem": "Informe mês, ano e fator de desafio."}), 400
    r = simular(e["vendedores"], mes, ano, fator, e["cfg"])
    if not r["avaliados"]:
        return jsonify({"status": "erro", "mensagem": "Nenhum vendedor com histórico suficiente neste mês. "
                        "Escolha um mês dentro do período da base (com ao menos 3 meses anteriores)."}), 400
    return jsonify({"status": "ok", **r})


@app.route("/api/fechamento", methods=["POST"])
def api_fechamento():
    e, b = _estado(), _json_body()
    try:
        mes, ano = int(b["mes"]), int(b["ano"])
        fator = float(b.get("fator_desafio", e["cfg"]["fator_desafio"]))
    except (KeyError, TypeError, ValueError):
        return jsonify({"status": "erro", "mensagem": "Informe mês, ano e fator de desafio."}), 400
    real = b.get("realizados", {})
    _, metas = sugerir_metas_time(e["vendedores"], mes, ano, fator, b.get("status_override"))
    linhas, sem_meta = [], []
    for m in metas:
        mrr = real.get(m["vendedor_id"])
        try:
            mrr = float(mrr) if mrr not in (None, "") else None
        except (TypeError, ValueError):
            mrr = None
        if mrr is None:
            continue
        if m["status"] not in ("ok", "historico_curto", "partida_a_frio") or not m["meta_sugerida"]:
            sem_meta.append({"nome": m["nome"], "motivo": m.get("mensagem", "Sem meta")})
            continue
        c = engine.calcular_comissao(mrr, m["meta_sugerida"], m["canal"], m["senioridade"], cfg=e["cfg"])
        linhas.append({"vendedor_id": m["vendedor_id"], "nome": m["nome"], "canal": m["canal"],
                       "senioridade": m["senioridade"], "status_meta": m["status"], "status_mes": m["status_mes"],
                       "meta": m["meta_sugerida"], **c})
    n = len(linhas)
    soma_meta = round(sum(l["meta"] for l in linhas), 2)
    soma_real = round(sum(l["mrr"] for l in linhas), 2)
    custo = round(sum(l["comissao_final"] for l in linhas), 2)
    contratado = round(sum(l["valor_contratado"] for l in linhas), 2)
    pcts = sorted(l["pct_atingido"] for l in linhas)
    resumo = {"n": n, "soma_metas": soma_meta, "soma_realizado": soma_real,
              "aderencia_time_pct": round(soma_real / soma_meta * 100, 1) if soma_meta else None,
              "elegiveis": sum(1 for l in linhas if l["elegivel"]),
              "pct_elegiveis": round(sum(1 for l in linhas if l["elegivel"]) / n * 100, 1) if n else None,
              "atingimento_mediano": round(pcts[len(pcts) // 2], 1) if pcts else None,
              "custo_comissoes": custo, "valor_contratado": contratado,
              "taxa_efetiva_pct": round(custo / contratado * 100, 2) if contratado else 0.0}
    meta_emp = b.get("meta_empresa")
    try:
        meta_emp = float(meta_emp) if meta_emp not in (None, "") else None
    except (TypeError, ValueError):
        meta_emp = None
    if meta_emp:
        resumo["meta_empresa"] = meta_emp
        resumo["diferenca_metas_vs_empresa_pct"] = round((soma_meta / meta_emp - 1) * 100, 1)
    return jsonify({"status": "ok", "mes": mes, "ano": ano, "resumo": resumo, "vendedores": linhas, "sem_meta": sem_meta})


@app.route("/api/evidencias")
def api_evidencias():
    with open(os.path.join(BASE, "data", "evidencias.json"), encoding="utf-8") as f:
        return jsonify(json.load(f))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"\n{'=' * 50}\n  DNZ Intelligence — http://localhost:{port}\n{'=' * 50}\n")
    app.run(host="0.0.0.0", port=port, debug=False)

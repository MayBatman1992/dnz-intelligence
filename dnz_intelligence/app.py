"""
DNZ Intelligence — Aplicação Web v2.1 (produção)
Compatível com Render.com
"""

from flask import Flask, render_template, request, jsonify, send_from_directory
import json, os
from engine     import calcular_comissao
from calibrador import sugerir_metas_time
from leitor     import ler_arquivo

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10MB

# Dataset em memória
_dataset = {"vendedores": [], "fonte": "exemplo"}


def _carregar_exemplo():
    caminho = os.path.join(os.path.dirname(__file__), "data", "exemplo_vendedores.json")
    with open(caminho, encoding="utf-8") as f:
        return json.load(f)["vendedores"]


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/template")
def baixar_template():
    return send_from_directory(
        os.path.join(os.path.dirname(__file__), "data"),
        "template_historico.xlsx",
        as_attachment=True,
        download_name="DNZ_template_historico.xlsx"
    )


@app.route("/api/upload", methods=["POST"])
def api_upload():
    global _dataset
    if "arquivo" not in request.files:
        return jsonify({"status": "erro", "mensagem": "Nenhum arquivo enviado."}), 400
    arquivo = request.files["arquivo"]
    if not arquivo.filename:
        return jsonify({"status": "erro", "mensagem": "Nome de arquivo inválido."}), 400
    resultado = ler_arquivo(arquivo.read(), arquivo.filename)
    if resultado["status"] == "ok":
        _dataset["vendedores"] = resultado["vendedores"]
        _dataset["fonte"]      = arquivo.filename
        return jsonify({
            "status":           "ok",
            "total_vendedores": resultado["total_vendedores"],
            "total_registros":  resultado["total_registros"],
            "vendedores": [
                {"id": v["id"], "nome": v["nome"],
                 "meses": len(v["historico"]),
                 "canal": v["canal"], "senioridade": v["senioridade"]}
                for v in resultado["vendedores"]
            ],
        })
    return jsonify(resultado), 400


@app.route("/api/usar_exemplo", methods=["POST"])
def api_usar_exemplo():
    global _dataset
    _dataset["vendedores"] = _carregar_exemplo()
    _dataset["fonte"]      = "exemplo"
    return jsonify({
        "status": "ok",
        "total_vendedores": len(_dataset["vendedores"]),
        "vendedores": [
            {"id": v["id"], "nome": v["nome"],
             "meses": len(v["historico"]),
             "canal": v["canal"], "senioridade": v["senioridade"]}
            for v in _dataset["vendedores"]
        ],
    })


@app.route("/api/dataset_atual", methods=["GET"])
def api_dataset_atual():
    vendedores = _dataset["vendedores"] or _carregar_exemplo()
    return jsonify({
        "fonte":            _dataset["fonte"],
        "total_vendedores": len(vendedores),
        "vendedores": [
            {"id": v["id"], "nome": v["nome"],
             "meses": len(v["historico"]),
             "canal": v["canal"], "senioridade": v["senioridade"]}
            for v in vendedores
        ],
    })


@app.route("/api/metas", methods=["POST"])
def api_metas():
    body      = request.json
    mes       = int(body.get("mes", 7))
    ano       = int(body.get("ano", 2025))
    fator     = float(body.get("fator_desafio", 1.10))
    vendedores = _dataset["vendedores"] or _carregar_exemplo()
    return jsonify(sugerir_metas_time(vendedores, mes, ano, fator))


@app.route("/api/comissao", methods=["POST"])
def api_comissao():
    body = request.json
    try:
        resultado = calcular_comissao(
            mrr=float(body["mrr"]), meta=float(body["meta"]),
            canal=body["canal"], senioridade=body["senioridade"],
        )
        return jsonify({"status": "ok", **resultado})
    except Exception as e:
        return jsonify({"status": "erro", "mensagem": str(e)}), 400


@app.route("/api/ciclo_completo", methods=["POST"])
def api_ciclo_completo():
    body       = request.json
    mes_alvo   = int(body.get("mes_alvo", 7))
    ano_alvo   = int(body.get("ano_alvo", 2025))
    fator      = float(body.get("fator_desafio", 1.10))
    realizados = body.get("realizados", {})
    vendedores = _dataset["vendedores"] or _carregar_exemplo()

    metas      = sugerir_metas_time(vendedores, mes_alvo, ano_alvo, fator)
    metas_dict = {m["vendedor_id"]: m for m in metas}

    relatorio, total_mrr, total_comissao, total_meta = [], 0, 0, 0

    for v in vendedores:
        vid  = v["id"]
        meta = metas_dict.get(vid, {})
        if meta.get("status") != "ok":
            relatorio.append({"id": vid, "nome": v["nome"],
                               "status": "sem_meta",
                               "mensagem": meta.get("mensagem", "Meta não gerada")})
            continue

        meta_valor = meta["meta_sugerida"]
        mrr_real   = float(realizados.get(vid, 0))
        comissao   = (calcular_comissao(mrr_real, meta_valor, v["canal"], v["senioridade"])
                      if mrr_real > 0
                      else {"mrr":0,"pct_atingido":0,"elegivel":False,
                            "acelerador":0,"coef_canal":0,"coef_senioridade":0,"comissao_final":0})

        total_mrr      += mrr_real
        total_comissao += comissao["comissao_final"]
        total_meta     += meta_valor

        relatorio.append({
            "id": vid, "nome": v["nome"],
            "canal": v["canal"], "senioridade": v["senioridade"],
            "meta": round(meta_valor, 2), "mrr_realizado": mrr_real,
            "pct_atingido": comissao["pct_atingido"],
            "elegivel": comissao["elegivel"],
            "acelerador": comissao["acelerador"],
            "comissao_final": comissao["comissao_final"],
            "diagnostico": meta.get("diagnostico", {}),
        })

    return jsonify({
        "mes_alvo": mes_alvo, "ano_alvo": ano_alvo,
        "total_mrr": round(total_mrr, 2),
        "total_meta": round(total_meta, 2),
        "total_comissao": round(total_comissao, 2),
        "vendedores": relatorio,
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"\n{'='*50}")
    print(f"  DNZ Intelligence — rodando na porta {port}")
    print(f"  Acesse: http://localhost:{port}")
    print(f"{'='*50}\n")
    app.run(host="0.0.0.0", port=port, debug=False)

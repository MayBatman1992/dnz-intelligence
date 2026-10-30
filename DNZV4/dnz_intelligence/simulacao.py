"""DNZ Intelligence — Simulação retrospectiva de cenários

Pergunta respondida: "Se eu tivesse usado estas metas neste mês, como teria ficado o time?"
Usa só o histórico ANTERIOR ao mês simulado para calibrar as metas e compara com o realizado.
Se a base trouxer a meta real (coluna 'meta'), compara também com ela.
"""
import statistics as st

import engine
from calibrador import preparar_contexto, sugerir_meta, _chave

FATORES_SWEEP = [1.00, 1.05, 1.10, 1.15, 1.20, 1.25, 1.30]


def _med(x):
    return round(st.median(x), 1) if x else None


def _resumo(linhas, fator, cfg, usar_meta_real=False):
    a = cfg["aceleracao"]
    itens = []
    for l in linhas:
        meta = l["meta_real"] if usar_meta_real else l["previsao"] * fator
        if not meta or meta <= 0:
            continue
        c = engine.calcular_comissao(l["real"], meta, l["canal"], l["senioridade"], cfg=cfg)
        itens.append({**l, "meta": meta, **c})
    n = len(itens)
    if n == 0:
        return {"n": 0}
    pcts = [i["pct_atingido"] for i in itens]
    custo = sum(i["comissao_final"] for i in itens)
    contratado = sum(i["valor_contratado"] for i in itens)
    soma_meta, soma_real = sum(i["meta"] for i in itens), sum(i["mrr"] for i in itens)
    q = lambda v, p: round(sorted(v)[min(len(v) - 1, int(p * (len(v) - 1) + 0.5))], 1)
    def grupo(chave):
        out = {}
        for k in sorted({i[chave] for i in itens}):
            g = [i for i in itens if i[chave] == k]
            cg = sum(i["comissao_final"] for i in g); tg = sum(i["valor_contratado"] for i in g)
            out[k] = {"n": len(g), "atingimento_mediano": _med([i["pct_atingido"] for i in g]),
                      "pct_elegiveis": round(sum(1 for i in g if i["elegivel"]) / len(g) * 100, 1),
                      "taxa_efetiva_pct": round(cg / tg * 100, 2) if tg else 0.0}
        return out
    return {
        "n": n, "fator_desafio": fator,
        "pct_elegiveis": round(sum(1 for i in itens if i["elegivel"]) / n * 100, 1),
        "pct_100": round(sum(1 for p in pcts if p >= 100) / n * 100, 1),
        "pct_teto": round(sum(1 for p in pcts if p > a["fim_faixa2"]) / n * 100, 1),
        "atingimento_mediano": _med(pcts), "atingimento_p25": q(pcts, .25), "atingimento_p75": q(pcts, .75),
        "custo_comissoes": round(custo, 2), "valor_contratado": round(contratado, 2),
        "taxa_efetiva_pct": round(custo / contratado * 100, 2) if contratado else 0.0,
        "soma_metas": round(soma_meta, 2), "soma_realizado": round(soma_real, 2),
        "aderencia_time_pct": round(soma_real / soma_meta * 100, 1) if soma_meta else None,
        "por_canal": grupo("canal"), "por_senioridade": grupo("senioridade"),
        "_itens": itens,
    }


def simular(vendedores, mes, ano, fator_desafio, cfg):
    ctx = preparar_contexto(vendedores, mes, ano)
    corte = ano * 12 + mes
    linhas, excluidos = [], {"partida_a_frio": 0, "historico_curto": 0, "sem_referencia": 0, "sem_base": 0}
    ativos = 0
    for v in vendedores:
        h = next((x for x in v["historico"] if _chave(x) == corte), None)
        if not h:
            continue
        ativos += 1
        r = sugerir_meta(v, mes, ano, ctx, 1.0)           # previsão pura; o desafio é aplicado depois
        if r["status"] != "ok":
            excluidos[r["status"]] = excluidos.get(r["status"], 0) + 1
            continue
        linhas.append({"vendedor_id": v["id"], "nome": v.get("nome", v["id"]),
                       "canal": h.get("canal", v.get("canal")), "senioridade": h.get("senioridade", v.get("senioridade")),
                       "status_mes": r["status_mes"], "previsao": r["previsao_central"], "real": h["mrr"],
                       "meta_real": h.get("meta")})
    principal = _resumo(linhas, fator_desafio, cfg)
    itens = principal.pop("_itens", [])
    sweep = []
    for f in FATORES_SWEEP:
        s = _resumo(linhas, f, cfg)
        s.pop("_itens", None)
        if s["n"]:
            sweep.append({k: s[k] for k in ("fator_desafio", "pct_elegiveis", "pct_100", "pct_teto",
                                           "atingimento_mediano", "custo_comissoes", "taxa_efetiva_pct", "aderencia_time_pct")})
    comparativo = None
    sub = [l for l in linhas if l.get("meta_real")]
    if len(sub) >= 5:                       # compara no MESMO conjunto de vendedores
        reais = _resumo(sub, 1.0, cfg, usar_meta_real=True)
        sug = _resumo(sub, fator_desafio, cfg)
        for x in (reais, sug):
            for k in ("_itens", "por_canal", "por_senioridade"):
                x.pop(k, None)
        comparativo = {"n": len(sub), "reais": reais, "sugeridas": sug}
    return {"mes": mes, "ano": ano, "vendedores_ativos": ativos, "avaliados": len(linhas),
            "excluidos": {k: v for k, v in excluidos.items() if v},
            "resumo": principal, "sweep": sweep, "comparativo_meta_real": comparativo,
            "detalhe": [{"vendedor_id": i["vendedor_id"], "nome": i["nome"], "canal": i["canal"],
                         "senioridade": i["senioridade"], "status_mes": i["status_mes"],
                         "meta": round(i["meta"], 2), "realizado": i["mrr"], "pct_atingido": i["pct_atingido"],
                         "elegivel": i["elegivel"], "acelerador": i["acelerador"],
                         "comissao": i["comissao_final"], "taxa_efetiva_pct": i["taxa_efetiva_pct"]} for i in itens],
            "fatores": {k: round(v, 3) for k, v in ctx["fatores"].items()}}

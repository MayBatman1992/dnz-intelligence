"""DNZ Intelligence — Módulo 1: Calibrador de Metas com IA
Algoritmo: Média Ponderada + Ajuste Sazonal + Fator de Desafio
"""

def _media_ponderada(valores, pesos):
    total = sum(pesos)
    return sum(v*p for v,p in zip(valores,pesos))/total if total else 0.0

def _tendencia(historico):
    if len(historico) < 2:
        return historico[0]["mrr"] if historico else 0.0
    hist = sorted(historico, key=lambda x: (x["ano"], x["mes"]))
    n = len(hist)
    return _media_ponderada([h["mrr"] for h in hist], list(range(1, n+1)))

def _fator_sazonal(historico, mes_alvo):
    mesmo_mes = [h["mrr"] for h in historico if h["mes"] == mes_alvo]
    todos     = [h["mrr"] for h in historico]
    if not mesmo_mes or not todos: return 1.0
    fator = (sum(mesmo_mes)/len(mesmo_mes)) / (sum(todos)/len(todos))
    return max(0.70, min(1.40, fator))

def _crescimento(historico):
    hist = sorted(historico, key=lambda x: (x["ano"], x["mes"]))
    if len(hist) < 2: return 0.0
    taxas = [(hist[i]["mrr"]-hist[i-1]["mrr"])/hist[i-1]["mrr"]
             for i in range(1,len(hist)) if hist[i-1]["mrr"]>0]
    return sum(taxas)/len(taxas) if taxas else 0.0

def sugerir_meta(vendedor_id, historico, mes_alvo, ano_alvo,
                 fator_desafio=1.10, minimo_meses=2):
    if len(historico) < minimo_meses:
        return {
            "vendedor_id": vendedor_id, "status": "historico_insuficiente",
            "meses_disponiveis": len(historico), "meses_necessarios": minimo_meses,
            "meta_sugerida": None,
            "mensagem": (f"Histórico insuficiente. Necessário: {minimo_meses} meses. "
                         f"Disponível: {len(historico)} mês(es). "
                         "O gestor deve definir a meta manualmente neste ciclo."),
        }
    tend  = _tendencia(historico)
    sazo  = _fator_sazonal(historico, mes_alvo)
    cresc = _crescimento(historico)
    meta  = tend * sazo * fator_desafio
    conf  = 0.15 if len(historico) < 4 else 0.08

    if cresc > 0.05:   tlabel = "crescimento forte"
    elif cresc > 0:    tlabel = "crescimento moderado"
    elif cresc > -0.05:tlabel = "estável"
    else:              tlabel = "queda"

    if sazo > 1.10:    slabel = "mês historicamente forte"
    elif sazo < 0.90:  slabel = "mês historicamente fraco"
    else:              slabel = "mês neutro"

    return {
        "vendedor_id": vendedor_id, "status": "ok",
        "mes_alvo": mes_alvo, "ano_alvo": ano_alvo,
        "meses_analisados": len(historico),
        "tendencia_mrr": round(tend, 2),
        "fator_sazonal": round(sazo, 4),
        "crescimento_mensal": round(cresc*100, 2),
        "fator_desafio": fator_desafio,
        "meta_sugerida": round(meta, 2),
        "meta_minima": round(meta*(1-conf), 2),
        "meta_maxima": round(meta*(1+conf), 2),
        "diagnostico": {"tendencia": tlabel, "sazonalidade": slabel},
    }

def sugerir_metas_time(vendedores, mes_alvo, ano_alvo, fator_desafio=1.10):
    resultados = []
    for v in vendedores:
        r = sugerir_meta(v["id"], v["historico"], mes_alvo, ano_alvo,
                         v.get("fator_desafio_custom", fator_desafio))
        r["nome"]        = v.get("nome", v["id"])
        r["canal"]       = v.get("canal", "inbound_crm")
        r["senioridade"] = v.get("senioridade", "pl")
        resultados.append(r)
    return resultados

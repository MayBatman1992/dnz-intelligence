"""DNZ Intelligence — Módulo 1: Calibrador de Metas

Método (regra explicável), escolhido por backtest em base real:

    Previsão = média dos últimos 3 meses CHEIOS do vendedor × fator do status do mês-alvo
    Meta     = Previsão × fator de desafio (decisão de política do gestor)

- O fator do status (Meta Cheia / Meta Parcial) é aprendido do histórico anterior ao mês-alvo
  (razão entre o realizado e a base). Sem linhas suficientes, usa o padrão (1,0 e 0,5).
- A faixa de variação vem do erro histórico (percentis 10 e 90 do realizado ÷ previsão).
- Vendedor com menos de 3 meses de histórico (partida a frio): o sistema NÃO calibra; mostra
  apenas uma referência inicial, de baixa confiança, baseada nos pares.
- Sazonalidade: não é aplicada (o backtest não a incluiu; exige histórico de 24 meses ou mais).
"""
import statistics as st

MIN_HIST = 3
N_BASE = 3
MIN_LINHAS = 30
FATORES_PADRAO = {"cheia": 1.0, "parcial": 0.5}
# Partida a frio: MRR do mês de rampagem ÷ MRR-base típico dos pares (mediana, base real interna).
FATORES_RAMPAGEM = {1: 0.34, 2: 0.50}
FAIXA_GENERICA = (0.65, 1.35)


def _chave(h):
    return h["ano"] * 12 + h["mes"]


def _rotulo(h):
    return f"{h['mes']:02d}/{h['ano']}"


def _status(h):
    t = str(h.get("obs", "") or "").lower()
    if "rampagem" in t:
        return "rampagem"
    if "parcial" in t:
        return "parcial"
    return "cheia"


def _br(v):
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _quantil(valores, q):
    v = sorted(valores)
    if not v:
        return None
    pos = (len(v) - 1) * q
    lo, hi = int(pos), min(int(pos) + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (pos - lo)


def _base(passado):
    """Média dos últimos N meses cheios (ou, se não houver, dos últimos N meses)."""
    cheios = [h for h in passado if _status(h) == "cheia"]
    usados = cheios[-N_BASE:] if cheios else passado[-N_BASE:]
    return (sum(h["mrr"] for h in usados) / len(usados)) if usados else 0.0, usados


def _historico(v):
    return sorted(v["historico"], key=_chave)


def preparar_contexto(vendedores, mes, ano):
    """Calcula uma única vez, para o time inteiro, tudo que depende só do mês-alvo."""
    corte = ano * 12 + mes
    pares, bases = [], []
    for v in vendedores:
        hist = _historico(v)
        for k in range(MIN_HIST, len(hist)):
            alvo = hist[k]
            if _chave(alvo) >= corte:
                break
            base, _ = _base(hist[:k])
            if base > 0:
                pares.append({"status": _status(alvo), "real": alvo["mrr"], "base": base})
        passado = [h for h in hist if _chave(h) < corte]
        if len(passado) >= MIN_HIST and corte - _chave(passado[-1]) <= 3:
            b, _ = _base(passado)
            if b > 0:
                bases.append({"base": b, "sen": passado[-1].get("senioridade", v.get("senioridade"))})

    fatores, origem, n_status = dict(FATORES_PADRAO), {}, {}
    for s in ("cheia", "parcial"):
        linhas = [p for p in pares if p["status"] == s]
        n_status[s] = len(linhas)
        if len(linhas) >= MIN_LINHAS:
            fatores[s] = sum(p["real"] for p in linhas) / sum(p["base"] for p in linhas)
            origem[s] = "historico"
        else:
            origem[s] = "padrao"

    faixas = {}
    for s in ("cheia", "parcial"):
        razoes = [p["real"] / (p["base"] * fatores[s]) for p in pares if p["status"] == s and fatores[s] > 0]
        if len(razoes) < MIN_LINHAS:
            razoes = [p["real"] / (p["base"] * fatores[p["status"]]) for p in pares
                      if p["status"] in fatores and fatores[p["status"]] > 0]
        if len(razoes) >= MIN_LINHAS:
            faixas[s] = (_quantil(razoes, 0.10), _quantil(razoes, 0.90), "historico")
        else:
            faixas[s] = (FAIXA_GENERICA[0], FAIXA_GENERICA[1], "generica")
    return {"corte": corte, "fatores": fatores, "origem_fatores": origem, "n_linhas": n_status,
            "faixas": faixas, "bases_pares": bases, "n_pares": len(pares)}


def _referencia_pares(ctx, sen):
    mesma = [b["base"] for b in ctx["bases_pares"] if b["sen"] == sen]
    usar = mesma if len(mesma) >= 5 else [b["base"] for b in ctx["bases_pares"]]
    return (st.median(usar), len(usar)) if usar else (None, 0)


def _tendencia(passado):
    cheios = [h["mrr"] for h in passado if _status(h) == "cheia"][-6:]
    if len(cheios) < 4:
        return "indisponível", None
    meio = len(cheios) // 2
    ini, fim = sum(cheios[:meio]) / meio, sum(cheios[meio:]) / (len(cheios) - meio)
    if ini <= 0:
        return "indisponível", None
    var = (fim / ini - 1) * 100
    return ("crescimento" if var > 10 else "queda" if var < -10 else "estável"), round(var, 1)


def sugerir_meta(v, mes, ano, ctx, fator_desafio=1.10, status_alvo=None):
    corte = ano * 12 + mes
    hist = _historico(v)
    passado = [h for h in hist if _chave(h) < corte]
    atual = next((h for h in hist if _chave(h) == corte), None)
    status = status_alvo or (_status(atual) if atual else "cheia")
    ultimo = passado[-1] if passado else (hist[0] if hist else {})
    res = {"vendedor_id": v["id"], "nome": v.get("nome", v["id"]),
           "canal": ultimo.get("canal", v.get("canal")),
           "senioridade": ultimo.get("senioridade", v.get("senioridade")),
           "status_mes": status, "meses_historico": len(passado), "fator_desafio": fator_desafio,
           "meta_sugerida": None, "previsao_central": None, "faixa_p10": None, "faixa_p90": None}
    n = len(passado)

    if n >= MIN_HIST:
        base, usados = _base(passado)
        if base <= 0:
            return {**res, "status": "sem_base", "mensagem": "Base de receita zerada; defina a meta manualmente."}
        f = ctx["fatores"].get(status, 1.0)
        prev = base * f
        faixa = ctx["faixas"].get(status) or ctx["faixas"]["cheia"]
        tend, var = _tendencia(passado)
        meta = prev * fator_desafio
        expl = (f"Base de {_br(base)} (média de {', '.join(_rotulo(h) for h in usados)}) × fator do status "
                f"“{status}” {f:.2f} = previsão de {_br(prev)}; × desafio {fator_desafio:.2f} = meta de {_br(meta)}.")
        return {**res, "status": "ok", "base_mrr": round(base, 2), "meses_base": [_rotulo(h) for h in usados],
                "fator_status": round(f, 4), "previsao_central": round(prev, 2),
                "faixa_p10": round(prev * faixa[0], 2), "faixa_p90": round(prev * faixa[1], 2),
                "faixa_origem": faixa[2], "meta_sugerida": round(meta, 2),
                "diagnostico": {"tendencia": tend, "variacao_pct": var}, "explicacao": expl}

    if n == 2 and status != "rampagem":
        base, usados = _base(passado)
        f = ctx["fatores"].get(status, 1.0)
        prev = base * f
        return {**res, "status": "historico_curto", "base_mrr": round(base, 2), "fator_status": round(f, 4),
                "previsao_central": round(prev, 2), "meta_sugerida": round(prev * fator_desafio, 2),
                "mensagem": "Apenas 2 meses de histórico: método não validado, confiança baixa. Revise manualmente.",
                "explicacao": f"Média de {n} meses ({_br(base)}) × fator {f:.2f}; confiança baixa."}

    ref, n_ref = _referencia_pares(ctx, res["senioridade"])
    if not ref:
        return {**res, "status": "sem_referencia",
                "mensagem": "Sem histórico próprio nem pares para referência. Defina a meta manualmente."}
    k = min(n + 1, 2)
    fr = FATORES_RAMPAGEM[k]
    meta = ref * fr
    return {**res, "status": "partida_a_frio", "mes_de_vida": n + 1, "referencia_pares": round(ref, 2),
            "fator_rampagem": fr, "previsao_central": round(meta, 2), "meta_sugerida": round(meta, 2),
            "mensagem": ("Vendedor com menos de 3 meses de histórico: referência inicial de baixa confiança "
                         "(erro típico validado em torno de 70%). Revise manualmente."),
            "explicacao": (f"Referência dos pares ({n_ref} vendedores) de {_br(ref)} × fator de rampagem do "
                           f"{k}º mês {fr:.2f} = {_br(meta)}. Não há calibração individual.")}


def sugerir_metas_time(vendedores, mes, ano, fator_desafio=1.10, status_override=None):
    ctx = preparar_contexto(vendedores, mes, ano)
    ov = status_override or {}
    metas = [sugerir_meta(v, mes, ano, ctx, fator_desafio, ov.get(v["id"])) for v in vendedores]
    return ctx, metas

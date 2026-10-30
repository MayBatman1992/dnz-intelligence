"""DNZ Intelligence — Motor de Comissionamento

    Comissão = MRR × Coef.Canal × Coef.Senioridade × Acelerador(% atingido da meta)

Valor contratado (TCV)  = MRR × meses de contrato (padrão: 12)
Taxa efetiva            = Comissão ÷ Valor contratado

Todos os parâmetros ficam em uma configuração (configurável por empresa).
Os valores padrão reproduzem o modelo validado em ambiente real.
Exemplo validado: R$ 15.720 × 1,0 (Inbound CRM) × 1,1 (Pleno) × 1,20 (144%) = R$ 20.750,40,
equivalente a 11,00% de R$ 188.640 contratados em 12 meses.
"""
import copy
import math

CONFIG_PADRAO = {
    "coef_canal": {"inbound_crm": 1.0, "inbound_prm": 1.4, "outbound": 1.6},
    "coef_senioridade": {"jr": 1.0, "pl": 1.1, "sr": 1.2},
    "aceleracao": {
        "limiar": 80.0,            # abaixo disso: não elegível
        "desconto_faixa1": 30.0,   # de 80% a 99%: (% - 30) / 100  -> 80% = 50% ... 99% = 69%
        "inicio_faixa2": 100.0,    # de 100% a 140%: 100% + 0,5 p.p. por 1 p.p. atingido
        "inclinacao_faixa2": 0.5,
        "fim_faixa2": 140.0,
        "teto": 1.20,              # acima de 140%: acelerador congelado em 120%
    },
    "arredondamento": "piso",      # "piso" (79,9% = 79%), "mais_proximo" ou "nenhum"
    "meses_contrato": 12,
    "fator_desafio": 1.10,
}

CANAIS = ("inbound_crm", "inbound_prm", "outbound")
SENIORIDADES = ("jr", "pl", "sr")
NOMES_CANAL = {"inbound_crm": "Inbound CRM", "inbound_prm": "Inbound PRM", "outbound": "Outbound"}
NOMES_SEN = {"jr": "Júnior", "pl": "Pleno", "sr": "Sênior"}


def config_padrao():
    return copy.deepcopy(CONFIG_PADRAO)


def _num(x, nome, minimo, maximo, erros):
    try:
        v = float(x)
    except (TypeError, ValueError):
        erros.append(f"'{nome}' deve ser numérico.")
        return None
    if not (minimo <= v <= maximo):
        erros.append(f"'{nome}' deve estar entre {minimo} e {maximo}.")
        return None
    return v


def validar_config(entrada):
    """Valida e normaliza uma configuração. Retorna (config, erros)."""
    cfg, erros = config_padrao(), []
    entrada = entrada or {}
    for grupo, chaves in (("coef_canal", CANAIS), ("coef_senioridade", SENIORIDADES)):
        for k in chaves:
            if k in entrada.get(grupo, {}):
                v = _num(entrada[grupo][k], f"{grupo}.{k}", 0, 5, erros)
                if v is not None:
                    cfg[grupo][k] = v
    lim = {"limiar": (0, 200), "desconto_faixa1": (0, 100), "inicio_faixa2": (0, 200),
           "inclinacao_faixa2": (0, 2), "fim_faixa2": (0, 400), "teto": (0, 5)}
    for k, (lo, hi) in lim.items():
        if k in entrada.get("aceleracao", {}):
            v = _num(entrada["aceleracao"][k], f"aceleracao.{k}", lo, hi, erros)
            if v is not None:
                cfg["aceleracao"][k] = v
    a = cfg["aceleracao"]
    if not (a["limiar"] <= a["inicio_faixa2"] <= a["fim_faixa2"]):
        erros.append("É preciso: limiar ≤ início da faixa 2 ≤ fim da faixa 2.")
    if entrada.get("arredondamento") in ("piso", "mais_proximo", "nenhum"):
        cfg["arredondamento"] = entrada["arredondamento"]
    elif "arredondamento" in entrada:
        erros.append("'arredondamento' deve ser piso, mais_proximo ou nenhum.")
    if "meses_contrato" in entrada:
        v = _num(entrada["meses_contrato"], "meses_contrato", 1, 60, erros)
        if v is not None:
            cfg["meses_contrato"] = int(v)
    if "fator_desafio" in entrada:
        v = _num(entrada["fator_desafio"], "fator_desafio", 0.5, 2.0, erros)
        if v is not None:
            cfg["fator_desafio"] = v
    return cfg, erros


def _pct_considerado(pct, modo):
    if modo == "piso":
        return math.floor(pct + 1e-9)
    if modo == "mais_proximo":
        return math.floor(pct + 0.5 + 1e-9)
    return pct


def calcular_acelerador(pct, cfg=None):
    cfg = cfg or CONFIG_PADRAO
    a = cfg["aceleracao"]
    p = _pct_considerado(pct, cfg.get("arredondamento", "piso"))
    if p < a["limiar"]:
        return 0.0
    if p < a["inicio_faixa2"]:
        return (p - a["desconto_faixa1"]) / 100.0
    if p <= a["fim_faixa2"]:
        return (100.0 + (p - a["inicio_faixa2"]) * a["inclinacao_faixa2"]) / 100.0
    return a["teto"]


def tabela_aceleradores(cfg=None):
    cfg = cfg or CONFIG_PADRAO
    a = cfg["aceleracao"]
    fim = int(a["fim_faixa2"])
    linhas = [{"pct": p, "acelerador": round(calcular_acelerador(p, cfg), 4)}
              for p in range(int(a["limiar"]), fim + 2)]
    return linhas


def calcular_comissao(mrr, meta, canal, senioridade, meses_contrato=None, cfg=None):
    cfg = cfg or CONFIG_PADRAO
    if meta <= 0:
        raise ValueError("Meta deve ser maior que zero.")
    meses = int(meses_contrato or cfg["meses_contrato"])
    if meses <= 0:
        raise ValueError("Meses de contrato deve ser maior que zero.")
    pct = mrr / meta * 100.0
    acel = calcular_acelerador(pct, cfg)
    cc = cfg["coef_canal"].get(str(canal).lower(), 1.0)
    cs = cfg["coef_senioridade"].get(str(senioridade).lower(), 1.0)
    comissao = mrr * cc * cs * acel if acel > 0 else 0.0
    contratado = mrr * meses
    return {
        "mrr": round(mrr, 2), "meta": round(meta, 2), "meses_contrato": meses,
        "valor_contratado": round(contratado, 2),
        "pct_atingido": round(pct, 2),
        "pct_considerado": _pct_considerado(pct, cfg.get("arredondamento", "piso")),
        "elegivel": acel > 0, "acelerador": round(acel, 4),
        "canal": canal, "coef_canal": cc, "senioridade": senioridade, "coef_senioridade": cs,
        "comissao_final": round(comissao, 2),
        "taxa_efetiva_pct": round(comissao / contratado * 100, 2) if contratado > 0 else 0.0,
    }


if __name__ == "__main__":
    r = calcular_comissao(15720, 15720 / 1.44, "inbound_crm", "pl")
    ok = (abs(r["comissao_final"] - 20750.40) < 0.01 and abs(r["valor_contratado"] - 188640) < 0.01
          and abs(r["taxa_efetiva_pct"] - 11.00) < 0.01)
    print(f"Comissão R$ {r['comissao_final']:,.2f} | Contratado R$ {r['valor_contratado']:,.2f} | "
          f"Taxa {r['taxa_efetiva_pct']}% | {'OK' if ok else 'ERRO'}")

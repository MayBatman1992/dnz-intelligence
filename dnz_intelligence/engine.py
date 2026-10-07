"""DNZ Intelligence — Motor de Comissionamento
Fórmula: Comissão = MRR × Coef.Canal × Coef.Senioridade × Acelerador
Validado: R$15.720 × 1.0 × 1.1 × 1.20 = R$20.750,40
"""

COEF_CANAL = {"inbound_crm": 1.0, "inbound_prm": 1.4, "outbound": 1.6}
COEF_SENIORIDADE = {"jr": 1.0, "pl": 1.1, "sr": 1.2}

def calcular_acelerador(pct: float) -> float:
    if pct < 80:       return 0.0
    elif pct <= 99:    return (pct - 30) / 100
    elif pct <= 140:   return (100 + (pct - 100) * 0.5) / 100
    else:              return 1.20

def calcular_comissao(mrr: float, meta: float, canal: str, senioridade: str) -> dict:
    if meta <= 0:
        raise ValueError("Meta deve ser maior que zero.")
    pct   = (mrr / meta) * 100
    acel  = calcular_acelerador(pct)
    cc    = COEF_CANAL.get(canal.lower(), 1.0)
    cs    = COEF_SENIORIDADE.get(senioridade.lower(), 1.0)
    comissao = mrr * cc * cs * acel if acel > 0 else 0.0
    return {
        "mrr": round(mrr, 2), "meta": round(meta, 2),
        "pct_atingido": round(pct, 2), "elegivel": acel > 0,
        "acelerador": round(acel, 4), "canal": canal,
        "coef_canal": cc, "senioridade": senioridade,
        "coef_senioridade": cs, "comissao_final": round(comissao, 2),
    }

if __name__ == "__main__":
    r = calcular_comissao(15720, 15720/1.44, "inbound_crm", "pl")
    ok = abs(r["comissao_final"] - 20750.40) < 0.01
    print(f"Validação: R${r['comissao_final']:,.2f} | {'✓ OK' if ok else '✗ ERRO'}")

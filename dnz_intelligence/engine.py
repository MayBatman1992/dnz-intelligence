"""DNZ Intelligence — Motor de Comissionamento

Fórmula:  Comissão = MRR × Coef.Canal × Coef.Senioridade × Acelerador
Receita contratada (valor total do contrato, TCV) = MRR × meses de contrato
Taxa efetiva = Comissão ÷ Receita contratada

Validado: R$15.720 × 1.0 × 1.1 × 1.20 = R$20.750,40
          (= 11,00% de R$188.640 contratados em 12 meses)
"""

COEF_CANAL = {"inbound_crm": 1.0, "inbound_prm": 1.4, "outbound": 1.6}
COEF_SENIORIDADE = {"jr": 1.0, "pl": 1.1, "sr": 1.2}
MESES_CONTRATO_PADRAO = 12  # todos os contratos do cenário validado são de 12 meses


def calcular_acelerador(pct: float) -> float:
    if pct < 80:       return 0.0
    elif pct <= 99:    return (pct - 30) / 100
    elif pct <= 140:   return (100 + (pct - 100) * 0.5) / 100
    else:              return 1.20


def calcular_comissao(mrr: float, meta: float, canal: str, senioridade: str,
                      meses_contrato: int = MESES_CONTRATO_PADRAO) -> dict:
    if meta <= 0:
        raise ValueError("Meta deve ser maior que zero.")
    if meses_contrato <= 0:
        raise ValueError("Meses de contrato deve ser maior que zero.")

    pct   = (mrr / meta) * 100
    acel  = calcular_acelerador(pct)
    cc    = COEF_CANAL.get(canal.lower(), 1.0)
    cs    = COEF_SENIORIDADE.get(senioridade.lower(), 1.0)
    comissao = mrr * cc * cs * acel if acel > 0 else 0.0

    valor_contratado = mrr * meses_contrato
    taxa_efetiva = (comissao / valor_contratado * 100) if valor_contratado > 0 else 0.0

    return {
        "mrr": round(mrr, 2), "meta": round(meta, 2),
        "meses_contrato": meses_contrato,
        "valor_contratado": round(valor_contratado, 2),
        "pct_atingido": round(pct, 2), "elegivel": acel > 0,
        "acelerador": round(acel, 4), "canal": canal,
        "coef_canal": cc, "senioridade": senioridade,
        "coef_senioridade": cs, "comissao_final": round(comissao, 2),
        "taxa_efetiva_pct": round(taxa_efetiva, 2),
    }


if __name__ == "__main__":
    r = calcular_comissao(15720, 15720/1.44, "inbound_crm", "pl")
    ok = (abs(r["comissao_final"] - 20750.40) < 0.01
          and abs(r["valor_contratado"] - 188640) < 0.01
          and abs(r["taxa_efetiva_pct"] - 11.00) < 0.01)
    print(f"Comissão R${r['comissao_final']:,.2f} | Contratado R${r['valor_contratado']:,.2f} "
          f"| Taxa {r['taxa_efetiva_pct']}% | {'✓ OK' if ok else '✗ ERRO'}")

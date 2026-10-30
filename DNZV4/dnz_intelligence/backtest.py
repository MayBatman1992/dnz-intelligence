"""
DNZ Intelligence — Backtest do Calibrador de Metas

Objetivo: medir QUAL método prevê melhor o MRR de cada vendedor no mês seguinte,
usando apenas informação disponível naquele momento (sem vazamento de dados).

Métodos comparados (mesmas previsões, mesmos meses, mesmos vendedores):
  1. Ingênuo ........ repete o último mês
  2. Média móvel 3m . média dos últimos 3 meses
  3. Heurística DNZ . tendência ponderada × fator sazonal (calibrador atual, sem o fator de desafio)
  4. Ridge .......... regressão linear regularizada (modelo único para todos os vendedores)
  5. Random Forest .. conjunto de árvores (modelo único para todos os vendedores)
  6. Gradient Boosting

Observação: o "fator de desafio" é uma decisão de política da empresa, não uma previsão.
Por isso ele fica de fora da comparação: aqui se mede a qualidade da PREVISÃO-BASE.

Uso:
    python backtest.py --sintetico                          (dados fictícios, para testar)
    python backtest.py --arquivo data/historico_real.xlsx   (seus dados, formato do template)
"""

import argparse
import os
import sys

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from calibrador import _fator_sazonal, _tendencia

MIN_HIST = 3        # meses anteriores exigidos para prever um mês
MIN_TREINO = 15     # linhas mínimas de treino para ajustar os modelos de ML
SEED = 42

CANAIS = ["inbound_crm", "inbound_prm", "outbound"]
SEN_ORD = {"jr": 0, "pl": 1, "sr": 2}


# ───────────────────────── dados sintéticos ─────────────────────────
def gerar_sintetico(n_vendedores=12, meses=24, seed=SEED):
    """Gera um time fictício com tendência, sazonalidade e ruído. NÃO são dados reais."""
    rng = np.random.default_rng(seed)
    sazon = {1: .92, 2: .90, 3: 1.0, 4: .98, 5: 1.02, 6: 1.0,
             7: .97, 8: 1.0, 9: 1.05, 10: 1.08, 11: 1.10, 12: 1.12}
    base_sen = {"jr": 6000, "pl": 9000, "sr": 14000}
    vendedores = []
    for i in range(n_vendedores):
        sen = str(rng.choice(["jr", "pl", "sr"], p=[.35, .40, .25]))
        canal = str(rng.choice(CANAIS, p=[.5, .25, .25]))
        base = base_sen[sen] * rng.lognormal(0, .15)
        cresc = rng.uniform(0.0, 0.025)
        inicio = int(rng.integers(0, 7))
        hist = []
        for m in range(inicio, meses):
            ano, mes = 2024 + m // 12, m % 12 + 1
            nivel = base * (1 + cresc) ** (m - inicio)
            mrr = nivel * sazon[mes] * rng.lognormal(0, .10)
            hist.append({"mes": mes, "ano": ano, "mrr": round(float(mrr), 2)})
        vendedores.append({"id": f"V{i+1:03d}", "nome": f"Vendedor {i+1}",
                           "canal": canal, "senioridade": sen, "historico": hist})
    return vendedores


# ───────────────────────── status do mês (observação) ─────────────────────────
def _obs(h):
    t = str(h.get("obs", "") or "")
    if "rampagem" in t: return "rampagem"
    if "parcial" in t:  return "parcial"
    if "cheia" in t:    return "cheia"
    return ""


# ───────────────────────── construção das linhas ─────────────────────────
def construir_linhas(vendedores):
    """Uma linha por (vendedor, mês-alvo). Features usam SOMENTE meses anteriores ao alvo."""
    linhas = []
    for v in vendedores:
        hist = sorted(v["historico"], key=lambda h: (h["ano"], h["mes"]))
        for k in range(MIN_HIST, len(hist)):
            passado, alvo = hist[:k], hist[k]
            vals = np.array([h["mrr"] for h in passado], dtype=float)
            base3 = vals[-3:].mean()
            cheios = [h for h in passado if _obs(h) in ("cheia", "")]
            vals_c = np.array([h["mrr"] for h in cheios], dtype=float)
            base = vals_c[-3:].mean() if len(vals_c) else base3   # base só com meses cheios
            if base <= 0 or alvo["mrr"] < 0:
                continue
            ult = vals[-6:]
            slope = np.polyfit(np.arange(len(ult)), ult, 1)[0] / base if len(ult) >= 3 else 0.0
            obs_alvo = _obs(alvo)
            feat = {
                "lag1": vals[-1] / base, "lag2": vals[-2] / base, "lag3": vals[-3] / base,
                "media_hist": vals.mean() / base, "slope": slope, "tempo_casa": k,
                "mes_sin": np.sin(2 * np.pi * alvo["mes"] / 12),
                "mes_cos": np.cos(2 * np.pi * alvo["mes"] / 12),
                "senioridade": SEN_ORD.get(alvo.get("senioridade", v["senioridade"]), 1),
            }
            for c in CANAIS:
                feat[f"canal_{c}"] = 1.0 if alvo.get("canal", v["canal"]) == c else 0.0
            feat["obs_parcial"] = 1.0 if obs_alvo == "parcial" else 0.0
            feat["obs_rampagem"] = 1.0 if obs_alvo == "rampagem" else 0.0
            feat["nc_ult3"] = float(sum(1 for h in passado[-3:] if _obs(h) not in ("cheia", "")))
            p_heur = _tendencia(passado) * _fator_sazonal(passado, alvo["mes"])
            p_heur_l = (_tendencia(cheios) * _fator_sazonal(cheios, alvo["mes"])) if len(cheios) else p_heur
            linhas.append({
                "idx": alvo["ano"] * 12 + alvo["mes"], "vendedor": v["id"],
                "real": alvo["mrr"], "base": base, "alvo_ratio": alvo["mrr"] / base,
                "cheia_alvo": 1 if obs_alvo in ("cheia", "") else 0,
                "status": obs_alvo if obs_alvo else "cheia",
                "p_ingenuo": vals[-1], "p_mm3": base3,
                "p_heuristica": p_heur,
                "p_mm3_limpo": base, "p_heur_limpo": p_heur_l,
                **feat,
            })
    return pd.DataFrame(linhas)


def modelos():
    return {
        "Ridge": make_pipeline(StandardScaler(), Ridge(alpha=5.0)),
        "Random Forest": RandomForestRegressor(n_estimators=200, max_depth=4, min_samples_leaf=3,
                                               random_state=SEED, n_jobs=1),
        "Gradient Boosting": GradientBoostingRegressor(n_estimators=150, max_depth=2,
                                                       learning_rate=0.05, subsample=0.8,
                                                       random_state=SEED),
    }


# ───────────────────────── backtest (janela expansível) ─────────────────────────
def rodar_backtest(vendedores):
    df = construir_linhas(vendedores)
    if df.empty:
        raise ValueError("Histórico insuficiente: nenhum vendedor tem meses suficientes.")
    cols = [c for c in df.columns if c not in
            ("idx", "vendedor", "real", "base", "alvo_ratio", "cheia_alvo", "status") and not c.startswith("p_")]

    previsoes = []
    for t in sorted(df["idx"].unique()):
        treino, teste = df[df["idx"] < t], df[df["idx"] == t].copy()
        if len(treino) < MIN_TREINO or teste.empty:
            continue
        # Regra explicável: média dos últimos 3 meses cheios × fator do status do mês-alvo,
        # com o fator estimado só nos meses anteriores (real ÷ base, por status).
        g = treino.groupby("status")[["real", "base"]].sum()
        fat = (g["real"] / g["base"]).to_dict()
        teste["p_regra"] = teste["base"] * teste["status"].map(fat).fillna(1.0)
        for nome, modelo in modelos().items():
            modelo.fit(treino[cols], treino["alvo_ratio"])
            teste[f"p_{nome}"] = modelo.predict(teste[cols]) * teste["base"]
        previsoes.append(teste)
    if not previsoes:
        raise ValueError(f"Poucos dados para treinar (mínimo {MIN_TREINO} linhas de treino). "
                         "São necessários mais vendedores ou mais meses.")
    return pd.concat(previsoes, ignore_index=True)


def metricas(df, col):
    erro = df[col] - df["real"]
    return {
        "Previsões avaliadas": len(df),
        "MAE (R$)": round(erro.abs().mean(), 2),
        "WAPE (%)": round(erro.abs().sum() / df["real"].sum() * 100, 2),
        "Viés (%)": round(erro.sum() / df["real"].sum() * 100, 2),
        "Dentro de ±10% (%)": round((erro.abs() / df["real"] <= 0.10).mean() * 100, 1),
    }


ROTULOS = {
    "p_ingenuo": "Ingênuo (último mês)", "p_mm3": "Média móvel 3m",
    "p_heuristica": "Heurística DNZ (atual)", "p_Ridge": "Ridge",
    "p_Random Forest": "Random Forest", "p_Gradient Boosting": "Gradient Boosting",
    "p_regra": "Regra explicável (meses cheios × fator do status)",
    "p_mm3_limpo": "Média móvel 3m (só meses cheios)",
    "p_heur_limpo": "Heurística DNZ (só meses cheios)",
}


def resumo(prev):
    linhas = []
    for col, rotulo in ROTULOS.items():
        linhas.append({"Método": rotulo, **metricas(prev, col)})
    return pd.DataFrame(linhas).sort_values("WAPE (%)").reset_index(drop=True)


def tabela_md(df):
    cab = "| " + " | ".join(df.columns) + " |"
    sep = "|" + "|".join(["---"] * len(df.columns)) + "|"
    corpo = ["| " + " | ".join(str(v) for v in linha) + " |" for linha in df.values]
    return "\n".join([cab, sep] + corpo)


def salvar(prev, tab, origem, tab_cheia=None, pasta="relatorios"):
    os.makedirs(pasta, exist_ok=True)
    tab.to_csv(os.path.join(pasta, "backtest_metricas.csv"), index=False, encoding="utf-8-sig")
    if tab_cheia is not None:
        tab_cheia.to_csv(os.path.join(pasta, "backtest_metricas_meses_cheios.csv"),
                         index=False, encoding="utf-8-sig")
    melhor = tab.iloc[0]
    heur = tab[tab["Método"] == "Heurística DNZ (atual)"].iloc[0]
    n_vend, n_prev = prev["vendedor"].nunique(), len(prev)
    md = [
        "# Backtest do Calibrador de Metas — DNZ Intelligence", "",
        f"**Origem dos dados:** {origem}",
        f"**Vendedores:** {n_vend} · **Previsões avaliadas:** {n_prev} · "
        f"**Período:** {int(prev['idx'].min())} a {int(prev['idx'].max())} (ano×12+mês)", "",
        "## Resultados (menor WAPE = melhor)", "",
        tabela_md(tab), "",
    ] + ([
        "## Somente meses de 'Meta Cheia' como alvo", "", tabela_md(tab_cheia), "",
    ] if tab_cheia is not None else []) + [
        "## Leitura", "",
        f"- Melhor método neste backtest: **{melhor['Método']}** (WAPE {melhor['WAPE (%)']}%).",
        f"- Heurística atual: WAPE {heur['WAPE (%)']}% e viés {heur['Viés (%)']}%.",
        "- WAPE = soma dos erros absolutos ÷ soma da receita real. Viés positivo = o método tende a superestimar.", "",
        "## Metodologia", "",
        "- Janela expansível: para cada mês, treina com meses anteriores e prevê o mês seguinte.",
        f"- Mínimo de {MIN_HIST} meses de histórico por vendedor e {MIN_TREINO} linhas de treino.",
        "- As variáveis de cada previsão usam apenas dados anteriores ao mês previsto (sem vazamento).",
        "- Modelos de ML treinados em conjunto, com alvo normalizado pela média dos últimos 3 meses do vendedor.",
        "- O fator de desafio fica fora da comparação: é decisão de política, não previsão.", "",
        "## Limitações", "",
        "- Amostra pequena: diferenças de poucos pontos percentuais podem ser ruído.",
        "- Sazonalidade só é aprendida com mais de 12 meses de histórico.",
        "- Meses de rampagem raramente são avaliados: o vendedor ainda não tem 3 meses de histórico (partida a frio).",
        "- A base não traz o valor da meta, então não mede atingimento nem equilíbrio entre vendedores.",
    ]
    with open(os.path.join(pasta, "backtest_relatorio.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(md))


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="Backtest do calibrador de metas")
    ap.add_argument("--arquivo", help="Excel/CSV no formato do template")
    ap.add_argument("--sintetico", action="store_true", help="Usa dados fictícios")
    args = ap.parse_args()

    if args.sintetico:
        vendedores, origem = gerar_sintetico(), "DADOS SINTÉTICOS (fictícios — não usar como resultado do TCC)"
    elif args.arquivo:
        from leitor import ler_arquivo
        if not os.path.exists(args.arquivo):
            sys.exit(f"Arquivo não encontrado: {args.arquivo}\n"
                     "Dica: use --arquivo seguido do caminho entre aspas.")
        with open(args.arquivo, "rb") as f:
            r = ler_arquivo(f.read(), os.path.basename(args.arquivo))
        if r["status"] != "ok":
            sys.exit(f"Erro ao ler arquivo: {r['mensagem']}")
        vendedores, origem = r["vendedores"], f"arquivo local ({os.path.basename(args.arquivo)})"
    else:
        sys.exit("Use --sintetico ou --arquivo caminho.xlsx")

    meses = [len(v["historico"]) for v in vendedores]
    mrrs = [h["mrr"] for v in vendedores for h in v["historico"]]
    print(f"\nConferência dos dados lidos: {len(vendedores)} vendedores | "
          f"meses por vendedor: mín {min(meses)}, máx {max(meses)} | "
          f"MRR médio por vendedor/mês: R$ {sum(mrrs)/len(mrrs):,.2f}")
    prev = rodar_backtest(vendedores)
    tab = resumo(prev)
    tem_obs = prev["cheia_alvo"].nunique() > 1
    tab_cheia = resumo(prev[prev["cheia_alvo"] == 1]) if tem_obs else None
    print(f"\nOrigem: {origem}")
    print(f"Vendedores: {prev['vendedor'].nunique()} | Previsões avaliadas: {len(prev)}\n")
    print("TODOS OS MESES")
    print(tab.to_string(index=False))
    if tab_cheia is not None:
        print(f"\nSOMENTE MESES DE META CHEIA COMO ALVO ({int(prev['cheia_alvo'].sum())} previsões)")
        print(tab_cheia.to_string(index=False))
    salvar(prev, tab, origem, tab_cheia)
    print("\n✓ Relatório salvo em relatorios/backtest_relatorio.md e backtest_metricas.csv")


if __name__ == "__main__":
    main()

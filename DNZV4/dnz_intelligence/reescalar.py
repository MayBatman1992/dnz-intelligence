"""
DNZ Intelligence — Reescalonamento de valores em R$ (para demonstração pública)

Multiplica as colunas monetárias por UM fator constante. Como o fator é o mesmo para
meta e para atingido, o % de atingimento, o acelerador e a taxa efetiva de comissão
não mudam; só o nível em R$ muda.

Uso (rode no seu computador, com os dados reais):
    python reescalar.py --arquivo Metas_Real.csv --fator 0.37 --colunas mrr meta --saida Metas_Demo.csv

IMPORTANTE: use o MESMO fator em todos os arquivos (histórico, metas...). Guarde o fator
em local privado e não o publique.
"""
import argparse, io, sys
import pandas as pd


def para_numero(x):
    if pd.isna(x): return float("nan")
    t = str(x).strip().replace("R$", "").replace(" ", "")
    if "," in t and "." in t: t = t.replace(".", "").replace(",", ".")
    elif "," in t: t = t.replace(",", ".")
    return float(t)


def formato_br(v):
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arquivo", required=True)
    ap.add_argument("--fator", type=float, required=True)
    ap.add_argument("--colunas", nargs="+", required=True, help="colunas em R$ (ex.: mrr meta)")
    ap.add_argument("--saida", required=True)
    a = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    raw = open(a.arquivo, "rb").read()
    texto = None
    for enc in ("utf-8-sig", "latin-1"):
        try: texto = raw.decode(enc); break
        except UnicodeDecodeError: continue
    df = pd.read_csv(io.StringIO(texto), sep=None, engine="python", dtype=str)
    df.columns = [c.strip().lower() for c in df.columns]
    for c in a.colunas:
        if c.lower() not in df.columns:
            sys.exit(f"Coluna '{c}' não encontrada. Colunas: {list(df.columns)}")
        df[c.lower()] = df[c.lower()].map(lambda x: formato_br(round(para_numero(x) * a.fator, 2)) if pd.notna(x) else x)
    if "nome" in df.columns:
        print("Aviso: o arquivo tem a coluna 'nome'. Remova ou pseudonimize antes de publicar.")
    df.to_csv(a.saida, sep=";", index=False, encoding="utf-8-sig")
    print(f"✓ {len(df)} linhas reescaladas (fator {a.fator}) -> {a.saida}")


if __name__ == "__main__":
    main()

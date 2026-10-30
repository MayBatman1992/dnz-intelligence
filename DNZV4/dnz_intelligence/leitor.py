"""DNZ Intelligence — Leitor de Arquivos Excel/CSV
Colunas obrigatórias: id, nome, mes, ano, mrr, canal, senioridade.
Colunas opcionais:    observacao (Meta Cheia / Meta Parcial / Rampagem) e meta (R$ da meta do mês).
Tolerante ao formato brasileiro: separador ';', vírgula decimal, 'R$', acentos e
rótulos como 'Inbound CRM' ou 'Sênior'.
"""
import io
import re
import unicodedata

import pandas as pd

COLUNAS = ["id", "nome", "mes", "ano", "mrr", "canal", "senioridade"]
CANAIS = {"inbound_crm", "inbound_prm", "outbound"}
SENIORS = {"jr", "pl", "sr"}
SINONIMOS_SEN = {"jr": "jr", "junior": "jr", "pl": "pl", "pleno": "pl",
                 "sr": "sr", "senior": "sr"}


def _sem_acento(t):
    return "".join(c for c in unicodedata.normalize("NFKD", str(t)) if not unicodedata.combining(c))


def _norm(t):
    return _sem_acento(t).strip().lower()


def _norm_canal(x):
    return re.sub(r"[\s\-]+", "_", _norm(x))


def _norm_sen(x):
    t = _norm(x)
    return SINONIMOS_SEN.get(t, t)


def _para_numero(x):
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return float("nan")
    if isinstance(x, (int, float)):
        return float(x)
    t = str(x).strip().replace("R$", "").replace(" ", "")
    if "," in t and "." in t:
        t = t.replace(".", "").replace(",", ".")
    elif "," in t:
        t = t.replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return float("nan")


def _ler_csv(conteudo: bytes) -> pd.DataFrame:
    texto = None
    for enc in ("utf-8-sig", "latin-1"):
        try:
            texto = conteudo.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    return pd.read_csv(io.StringIO(texto), sep=None, engine="python", dtype=str)


def ler_arquivo(conteudo: bytes, nome: str) -> dict:
    try:
        n = nome.lower()
        if n.endswith((".xlsx", ".xls")):
            df = pd.read_excel(io.BytesIO(conteudo))
        elif n.endswith(".csv"):
            df = _ler_csv(conteudo)
        else:
            return {"status": "erro", "mensagem": "Formato não suportado. Use .xlsx ou .csv"}
    except Exception as e:
        return {"status": "erro", "mensagem": f"Erro ao ler arquivo: {e}"}

    df.columns = [_norm(c) for c in df.columns]
    df = df.dropna(how="all")

    faltando = [c for c in COLUNAS if c not in df.columns]
    if faltando:
        return {"status": "erro",
                "mensagem": f"Colunas obrigatórias ausentes: {faltando}. "
                            f"Colunas encontradas no arquivo: {list(df.columns)}"}

    df["canal"] = df["canal"].map(_norm_canal)
    df["senioridade"] = df["senioridade"].map(_norm_sen)

    erros = []
    inv_canal = sorted(set(df["canal"]) - CANAIS)
    if inv_canal:
        erros.append(f"Canais não reconhecidos: {inv_canal}. Aceitos: inbound_crm, inbound_prm, outbound")
    inv_sen = sorted(set(df["senioridade"]) - SENIORS)
    if inv_sen:
        erros.append(f"Senioridades não reconhecidas: {inv_sen}. Aceitas: jr, pl, sr")

    tem_meta = "meta" in df.columns
    if tem_meta:
        df["meta"] = df["meta"].map(_para_numero)
    df["mes"] = pd.to_numeric(df["mes"], errors="coerce")
    df["ano"] = pd.to_numeric(df["ano"], errors="coerce")
    df["mrr"] = df["mrr"].map(_para_numero)
    if df[["mes", "ano", "mrr"]].isna().any().any():
        erros.append("Há valores vazios ou não numéricos em 'mes', 'ano' ou 'mrr'.")
    elif not df["mes"].between(1, 12).all():
        erros.append("A coluna 'mes' deve ter valores de 1 a 12.")
    elif (df["mrr"] < 0).any():
        erros.append("A coluna 'mrr' tem valores negativos.")
    if erros:
        return {"status": "erro", "mensagem": " | ".join(erros)}

    df["mes"] = df["mes"].astype(int)
    df["ano"] = df["ano"].astype(int)

    vendedores = []
    for vid, grupo in df.groupby("id"):
        grupo = grupo.sort_values(["ano", "mes"])
        primeiro = grupo.iloc[-1]   # atributos atuais = mês mais recente
        historico = []
        for _, r in grupo.iterrows():
            item = {"mes": int(r["mes"]), "ano": int(r["ano"]), "mrr": float(r["mrr"]),
                    "canal": str(r["canal"]), "senioridade": str(r["senioridade"])}
            if tem_meta and pd.notna(r["meta"]) and r["meta"] > 0:
                item["meta"] = float(r["meta"])
            if "observacao" in grupo.columns:
                obs = r["observacao"]
                item["obs"] = "" if (obs is None or (isinstance(obs, float) and pd.isna(obs))) else _norm(obs)
            historico.append(item)
        historico.sort(key=lambda x: (x["ano"], x["mes"]))
        vendedores.append({
            "id": str(vid), "nome": str(primeiro["nome"]),
            "canal": str(primeiro["canal"]),
            "senioridade": str(primeiro["senioridade"]),
            "historico": historico,
        })

    return {"status": "ok", "total_registros": len(df),
            "total_vendedores": len(vendedores), "vendedores": vendedores}

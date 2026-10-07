"""DNZ Intelligence — Leitor de Arquivos Excel/CSV"""
import pandas as pd
import io

COLUNAS = ["id","nome","mes","ano","mrr","canal","senioridade"]
CANAIS  = {"inbound_crm","inbound_prm","outbound"}
SENIORS = {"jr","pl","sr"}

def ler_arquivo(conteudo: bytes, nome: str) -> dict:
    try:
        if nome.endswith((".xlsx",".xls")):
            df = pd.read_excel(io.BytesIO(conteudo))
        elif nome.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(conteudo))
        else:
            return {"status":"erro","mensagem":"Formato não suportado. Use .xlsx ou .csv"}
    except Exception as e:
        return {"status":"erro","mensagem":f"Erro ao ler arquivo: {e}"}

    df.columns = df.columns.str.strip().str.lower()
    df = df.dropna(how="all")

    erros = []
    for c in COLUNAS:
        if c not in df.columns:
            erros.append(f"Coluna obrigatória ausente: '{c}'")
    if erros:
        return {"status":"erro","mensagem":" | ".join(erros)}

    inv_canal = set(df["canal"].str.lower().unique()) - CANAIS
    if inv_canal:
        erros.append(f"Canais inválidos: {inv_canal}. Use: inbound_crm, inbound_prm, outbound")

    inv_sen = set(df["senioridade"].str.lower().unique()) - SENIORS
    if inv_sen:
        erros.append(f"Senioridades inválidas: {inv_sen}. Use: jr, pl, sr")

    if erros:
        return {"status":"erro","mensagem":" | ".join(erros)}

    df["canal"]       = df["canal"].str.strip().str.lower()
    df["senioridade"] = df["senioridade"].str.strip().str.lower()
    df["mrr"]         = pd.to_numeric(df["mrr"], errors="coerce").fillna(0)
    df["mes"]         = df["mes"].astype(int)
    df["ano"]         = df["ano"].astype(int)

    vendedores = []
    for vid, grupo in df.groupby("id"):
        primeiro = grupo.iloc[0]
        historico = sorted([
            {"mes": int(r["mes"]), "ano": int(r["ano"]), "mrr": float(r["mrr"])}
            for _, r in grupo.iterrows()
        ], key=lambda x: (x["ano"], x["mes"]))
        vendedores.append({
            "id": str(vid), "nome": str(primeiro["nome"]),
            "canal": str(primeiro["canal"]),
            "senioridade": str(primeiro["senioridade"]),
            "historico": historico,
        })

    return {
        "status": "ok",
        "total_registros": len(df),
        "total_vendedores": len(vendedores),
        "vendedores": vendedores,
    }

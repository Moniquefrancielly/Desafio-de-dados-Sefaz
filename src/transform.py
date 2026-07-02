"""
Passo 2 — Leitura, limpeza e consolidação dos CSVs do FINBRA em um único
DataFrame, e geração do Parquet final.

Pegadinhas do formato tratadas aqui (ver README do desafio):
- Encoding ISO-8859-1 (Latin-1), não UTF-8.
- Separador de colunas ';', não ','.
- Separador decimal ',', não '.'.
- 3 linhas de metadados antes do cabeçalho real.
"""

from pathlib import Path
import re

import pandas as pd

INTERIM_DIR = Path("data/interim")
PROCESSED_DIR = Path("data/processed")
OUTPUT_PARQUET = PROCESSED_DIR / "finbra.parquet"


def read_year_csv(csv_path: Path, ano: int) -> pd.DataFrame:
    """Lê um finbra.csv de um ano específico já tratando as pegadinhas do formato."""
    df = pd.read_csv(
        csv_path,
        sep=";",
        skiprows=3,          # pula as 3 linhas de metadados (Exercício/Escopo/Tabela)
        encoding="latin-1",  # ISO-8859-1, evita quebrar acentuação
        decimal=",",         # vírgula é o separador decimal (874885274,98)
        thousands=".",       # ponto como separador de milhar, se houver
    )
    df["ano"] = ano
    return df


def classify_conta(conta: str) -> str:
    """Classifica a coluna 'Conta' em funcao / subfuncao / agregado.

    - Função: código de 2 dígitos antes do ' - ' (ex.: '10 - Saúde')
    - Subfunção: código XX.YYY antes do ' - ' (ex.: '10.301 - Atenção Básica')
    - Agregado: linhas de totais ou 'FUxx - Demais Subfunções', que não devem
      ser somadas junto com funções/subfunções para evitar dupla contagem.
    """
    if not isinstance(conta, str):
        return "desconhecido"

    codigo = conta.split(" - ")[0].strip()

    if re.fullmatch(r"\d{2}\.\d{3}", codigo):
        return "subfuncao"
    if re.fullmatch(r"\d{2}", codigo):
        return "funcao"
    return "agregado"


def extract_codigo_funcao(conta: str) -> str | None:
    """Extrai apenas o código de função (2 dígitos), usado como chave de junção
    para montar a cascata função -> subfunção (não vai para o dataset final sozinho)."""
    if not isinstance(conta, str):
        return None
    codigo = conta.split(" - ")[0].strip()
    if re.fullmatch(r"\d{2}\.\d{3}", codigo):
        return codigo.split(".")[0]
    if re.fullmatch(r"\d{2}", codigo):
        return codigo
    return None


def add_funcao_subfuncao_cascata(df: pd.DataFrame) -> pd.DataFrame:
    """Monta a cascata função -> subfunção com nomes completos, conforme
    orientação: não isolar em 'função: 03, subfunção: 092', e sim manter
    'função: 03 - Essencial à Justiça' e 'subfuncao: 03.092 - Representação
    Judicial e Extrajudicial'.

    Como a subfunção é matricial (a mesma subfunção pode aparecer em várias
    funções, ex.: 122 - Administração Geral em 04.122, 10.122, 12.122...),
    a junção é feita pelo código de função (2 dígitos) e não pelo texto.
    """
    # Mapa código de função (2 dígitos) -> nome completo (ex.: "10 - Saúde"),
    # construído a partir das próprias linhas do tipo 'funcao'
    lookup_funcao = (
        df.loc[df["tipo_conta"] == "funcao", ["codigo_funcao", "Conta"]]
        .drop_duplicates()
        .set_index("codigo_funcao")["Conta"]
        .to_dict()
    )

    df["funcao"] = df["codigo_funcao"].map(lookup_funcao)
    df["subfuncao"] = df["Conta"].where(df["tipo_conta"] == "subfuncao")

    return df


def consolidate(interim_dir: Path = INTERIM_DIR) -> pd.DataFrame:
    """Lê todos os CSVs extraídos e consolida em um único DataFrame limpo."""
    frames = []

    for year_folder in sorted(interim_dir.iterdir()):
        if not year_folder.is_dir():
            continue
        csv_path = year_folder / "finbra.csv"
        if not csv_path.exists():
            continue

        ano = int(year_folder.name)
        df_ano = read_year_csv(csv_path, ano)
        frames.append(df_ano)
        print(f"[ok] {ano}: {len(df_ano):,} linhas lidas")

    df = pd.concat(frames, ignore_index=True)

    # Garante que Valor é numérico (caso alguma linha tenha vindo como texto)
    df["Valor"] = pd.to_numeric(df["Valor"], errors="coerce")

    # Classifica cada linha de 'Conta' em funcao / subfuncao / agregado
    df["tipo_conta"] = df["Conta"].apply(classify_conta)
    df["codigo_funcao"] = df["Conta"].apply(extract_codigo_funcao)

    # Monta a cascata função -> subfunção com nomes completos (orientação do José
    # no grupo: não separar em código+nome isolados, e sim manter o texto cheio
    # de cada nível, ligados pelo código de função)
    df = add_funcao_subfuncao_cascata(df)

    # Checagem importante: completude por ano (não comparar 2025 incompleto
    # com anos completos de 26 capitais)
    completude = df.groupby("ano")["Instituição"].nunique()
    print("\nCapitais presentes por ano:")
    print(completude)

    return df


def save_parquet(df: pd.DataFrame, output_path: Path = OUTPUT_PARQUET) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(output_path, index=False)
    print(f"\n[ok] Parquet salvo em {output_path} ({len(df):,} linhas)")


if __name__ == "__main__":
    df = consolidate()
    save_parquet(df)
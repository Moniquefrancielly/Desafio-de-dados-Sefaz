"""
Orquestra o pipeline completo: extração -> transformação -> validação de consulta.

Uso:
    python src/run_pipeline.py
"""

from pathlib import Path

from extract import extract_all
from transform import consolidate, save_parquet
from database import get_connection, taxa_execucao_por_funcao

RAW_DIR = Path("dados_compactos")  # pasta já existente no repo original do desafio
INTERIM_DIR = Path("data/interim")
PARQUET_PATH = Path("data/processed/finbra.parquet")


def main() -> None:
    print("=" * 60)
    print("PASSO 1 — Extraindo os .zip de dados_compactos/<ano>/")
    print("=" * 60)
    extracted = extract_all(RAW_DIR, INTERIM_DIR)
    if not extracted:
        print("[erro] Nenhum arquivo extraído. Verifique se os .zip estão em data/raw/<ano>/.")
        return

    print("\n" + "=" * 60)
    print("PASSO 2 — Consolidando e limpando os dados")
    print("=" * 60)
    df = consolidate(INTERIM_DIR)
    save_parquet(df, PARQUET_PATH)

    print("\n" + "=" * 60)
    print("PASSO 3 — Validando consulta via DuckDB")
    print("=" * 60)
    con = get_connection(PARQUET_PATH)
    ultimo_ano_completo = int(df["ano"].max()) - 1  # 2025 costuma estar incompleto
    resultado = taxa_execucao_por_funcao(con, ano=ultimo_ano_completo).df()
    print(f"\nAmostra da taxa de execução por função ({ultimo_ano_completo}):")
    print(resultado.head(10))

    print("\n[ok] Pipeline concluído com sucesso.")


if __name__ == "__main__":
    main()
"""
Passo 3 — Camada de consulta usando DuckDB diretamente sobre o Parquet.

Não "injetamos" os dados em tabelas: o DuckDB lê o Parquet direto do disco
(columnar + compressão), então basta registrar uma view e consultar com SQL.
Isso mantém o projeto leve e portátil, sem precisar subir/manter um banco.

Tanto o notebook de EDA quanto o app Streamlit devem importar get_connection()
daqui, para não duplicar a lógica de conexão.
"""

from pathlib import Path

import duckdb

PARQUET_PATH = Path("data/processed/finbra.parquet")


def get_connection(parquet_path: Path = PARQUET_PATH) -> duckdb.DuckDBPyConnection:
    """Retorna uma conexão DuckDB com a view 'despesas' já registrada."""
    con = duckdb.connect(database=":memory:")
    con.execute(f"""
        CREATE VIEW despesas AS
        SELECT * FROM read_parquet('{parquet_path.as_posix()}')
    """)
    return con


def taxa_execucao_por_funcao(con: duckdb.DuckDBPyConnection, ano: int) -> "duckdb.DuckDBPyRelation":
    """Exemplo de consulta: taxa de execução (Pago / Empenhado) por capital e função."""
    query = """
        WITH base AS (
            SELECT
                "Instituição" AS capital,
                "UF" AS uf,
                funcao,
                ano,
                "Coluna" AS estagio,
                SUM("Valor") AS valor
            FROM despesas
            WHERE tipo_conta = 'funcao'
              AND ano = ?
              AND "Coluna" IN ('Despesas Empenhadas', 'Despesas Pagas')
            GROUP BY 1, 2, 3, 4, 5
        )
        SELECT
            capital,
            uf,
            funcao,
            MAX(CASE WHEN estagio = 'Despesas Empenhadas' THEN valor END) AS empenhado,
            MAX(CASE WHEN estagio = 'Despesas Pagas' THEN valor END) AS pago,
            ROUND(
                100.0 * MAX(CASE WHEN estagio = 'Despesas Pagas' THEN valor END)
                / NULLIF(MAX(CASE WHEN estagio = 'Despesas Empenhadas' THEN valor END), 0),
                1
            ) AS taxa_execucao_pct
        FROM base
        GROUP BY capital, uf, funcao
        ORDER BY taxa_execucao_pct DESC
    """
    return con.execute(query, [ano])


def completude_por_ano(con: duckdb.DuckDBPyConnection, total_capitais: int = 26) -> "duckdb.DuckDBPyRelation":
    """Quantas capitais reportaram dados em cada ano, e o % de completude.

    Útil para o Streamlit mostrar algo como 'X/26 capitais reportaram em 2025'
    e para justificar por que 2025 não deve ser comparado diretamente com
    anos anteriores.
    """
    query = """
        SELECT
            ano,
            COUNT(DISTINCT "Instituição") AS capitais_reportadas,
            ? AS total_capitais,
            ROUND(100.0 * COUNT(DISTINCT "Instituição") / ?, 1) AS completude_pct
        FROM despesas
        GROUP BY ano
        ORDER BY ano
    """
    return con.execute(query, [total_capitais, total_capitais])


def capitais_ausentes(con: duckdb.DuckDBPyConnection, ano: int) -> "duckdb.DuckDBPyRelation":
    """Lista quais capitais existiram em algum ano do dataset, mas não aparecem no ano informado.

    Útil para destacar, por exemplo, quais capitais ainda não declararam 2025.
    """
    query = """
        WITH todas_capitais AS (
            SELECT DISTINCT "Instituição" AS capital, "UF" AS uf FROM despesas
        ),
        capitais_no_ano AS (
            SELECT DISTINCT "Instituição" AS capital FROM despesas WHERE ano = ?
        )
        SELECT t.capital, t.uf
        FROM todas_capitais t
        LEFT JOIN capitais_no_ano c ON t.capital = c.capital
        WHERE c.capital IS NULL
        ORDER BY t.capital
    """
    return con.execute(query, [ano])


if __name__ == "__main__":
    con = get_connection()

    print("Completude por ano:")
    print(completude_por_ano(con).df())

    print("\nExemplo — taxa de execução por função (2023):")
    resultado = taxa_execucao_por_funcao(con, ano=2023).df()
    print(resultado.head(20))
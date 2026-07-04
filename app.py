from pathlib import Path

import duckdb
import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="Despesas das Capitais — FINBRA", layout="wide")

PROJECT_ROOT = Path(__file__).parent
PARQUET_PATH = PROJECT_ROOT / "data" / "processed" / "finbra.parquet"

MACEIO = "Prefeitura Municipal de Maceió - AL"


@st.cache_resource
def get_connection():
    con = duckdb.connect(":memory:")
    con.execute(f"CREATE VIEW despesas AS SELECT * FROM read_parquet('{PARQUET_PATH.as_posix()}')")
    return con


con = get_connection()


@st.cache_data
def carregar_listas():
    anos = con.execute(
        "SELECT DISTINCT ano FROM despesas WHERE ano BETWEEN 2020 AND 2024 ORDER BY ano"
    ).df()["ano"].tolist()
    capitais = con.execute(
        "SELECT DISTINCT \"Instituição\" FROM despesas ORDER BY 1"
    ).df()["Instituição"].tolist()
    funcoes = con.execute(
        "SELECT DISTINCT funcao FROM despesas WHERE tipo_conta = 'funcao' ORDER BY 1"
    ).df()["funcao"].dropna().tolist()
    return anos, capitais, funcoes


anos_disponiveis, capitais_disponiveis, funcoes_disponiveis = carregar_listas()


def indice_capital_padrao():
    return capitais_disponiveis.index(MACEIO) if MACEIO in capitais_disponiveis else 0


# SIDEBAR — filtros globais
st.sidebar.title("Filtros")
capital_selecionada = st.sidebar.selectbox(
    "Capital em destaque", capitais_disponiveis, index=indice_capital_padrao()
)
ano_selecionado = st.sidebar.selectbox(
    "Ano de referência (indicadores pontuais)", anos_disponiveis, index=len(anos_disponiveis) - 1
)
st.sidebar.caption(
    "2025 foi excluído das comparações por estar incompleto "
    "(11 de 26 capitais reportaram até o momento)."
)

nome_curto = capital_selecionada.replace("Prefeitura Municipal de ", "").replace(" - ", "/")

st.title("📊 Despesas por Função — Capitais Brasileiras (2020-2024)")
st.caption("Fonte: FINBRA/Siconfi, Anexo I-E (Despesas por Função). Analisando apenas o lado da despesa pública.")

tab_geral, tab_execucao, tab_percapita, tab_estrutura, tab_padrao, tab_temporal, tab_maceio = st.tabs(
    ["🗺️ Visão Geral", "✅ Execução", "👥 Per Capita", "🏛️ Estrutura do Gasto",
     "🎯 Padrão Geral", "📈 Evolução Temporal", "🔎 Foco em Maceió"]
)

# ABA 1 — Visão geral
with tab_geral:
    st.subheader("Completude dos dados por ano")

    df_completude = con.execute("""
        SELECT ano, COUNT(DISTINCT "Instituição") AS capitais_reportadas
        FROM despesas GROUP BY ano ORDER BY ano
    """).df()
    df_completude["completude_pct"] = round(100 * df_completude["capitais_reportadas"] / 26, 1)

    col1, col2 = st.columns([2, 1])
    fig_completude = px.bar(
        df_completude, x="ano", y="capitais_reportadas", text="capitais_reportadas",
        labels={"ano": "Ano", "capitais_reportadas": "Capitais reportadas"},
        title="Quantas das 26 capitais reportaram dados, por ano",
    )
    fig_completude.add_hline(y=26, line_dash="dash", line_color="gray")
    col1.plotly_chart(fig_completude, use_container_width=True)
    col2.dataframe(df_completude, hide_index=True, use_container_width=True)

    st.info(
        "⚠️ 2025 está incompleto (apenas 11/26 capitais). Por isso, todas as "
        "comparações entre capitais neste app usam 2024 como ano de referência "
        "mais recente com dado completo."
    )

    st.subheader(f"Panorama — {capital_selecionada}, {ano_selecionado}")
    df_resumo = con.execute("""
        SELECT funcao, "Coluna" AS estagio, SUM("Valor") AS valor
        FROM despesas
        WHERE tipo_conta = 'funcao' AND ano = ? AND "Instituição" = ?
          AND "Coluna" IN ('Despesas Empenhadas', 'Despesas Pagas')
        GROUP BY funcao, "Coluna"
    """, [ano_selecionado, capital_selecionada]).df()

    total_empenhado = df_resumo[df_resumo["estagio"] == "Despesas Empenhadas"]["valor"].sum()
    total_pago = df_resumo[df_resumo["estagio"] == "Despesas Pagas"]["valor"].sum()
    taxa_geral = 100 * total_pago / total_empenhado if total_empenhado else 0

    c1, c2, c3 = st.columns(3)
    c1.metric("Total empenhado", f"R$ {total_empenhado/1e9:.2f} bi")
    c2.metric("Total pago", f"R$ {total_pago/1e9:.2f} bi")
    c3.metric("Taxa de execução geral", f"{taxa_geral:.1f}%")

# ABA 2 — Execução (Empenhado x Pago)
with tab_execucao:
    st.subheader(f"Taxa de execução por função — {ano_selecionado}")

    query_execucao = """
        WITH base AS (
            SELECT "Instituição" AS capital, funcao, "Coluna" AS estagio, SUM("Valor") AS valor
            FROM despesas
            WHERE tipo_conta = 'funcao' AND ano = ?
              AND "Coluna" IN ('Despesas Empenhadas', 'Despesas Pagas')
            GROUP BY 1, 2, 3
        )
        SELECT
            capital, funcao,
            MAX(CASE WHEN estagio = 'Despesas Empenhadas' THEN valor END) AS empenhado,
            MAX(CASE WHEN estagio = 'Despesas Pagas' THEN valor END) AS pago,
            ROUND(100.0 * MAX(CASE WHEN estagio = 'Despesas Pagas' THEN valor END)
                  / NULLIF(MAX(CASE WHEN estagio = 'Despesas Empenhadas' THEN valor END), 0), 1) AS taxa_execucao_pct
        FROM base GROUP BY capital, funcao
    """
    df_execucao = con.execute(query_execucao, [ano_selecionado]).df().dropna(subset=["taxa_execucao_pct"])

    with st.expander(f"🔻 Ranking geral — piores execuções entre todas as capitais e funções, {ano_selecionado}", expanded=False):
        n_piores = st.slider("Quantas linhas mostrar", 5, 50, 15, key="n_piores_execucao")
        st.dataframe(
            df_execucao.sort_values("taxa_execucao_pct").head(n_piores),
            hide_index=True, use_container_width=True,
        )

    df_capital = df_execucao[df_execucao["capital"] == capital_selecionada]
    media_funcao = (
        df_execucao.groupby("funcao")["taxa_execucao_pct"].mean()
        .reset_index().rename(columns={"taxa_execucao_pct": "media_capitais"})
    )
    comparativo = df_capital.merge(media_funcao, on="funcao").sort_values("taxa_execucao_pct")
    comparativo["diferenca"] = comparativo["taxa_execucao_pct"] - comparativo["media_capitais"]

    col1, col2 = st.columns(2)

    fig_exec = px.bar(
        comparativo, x="taxa_execucao_pct", y="funcao", orientation="h",
        labels={"taxa_execucao_pct": "Taxa de execução (%)", "funcao": ""},
        title=f"{nome_curto} — taxa de execução por função",
    )
    fig_exec.add_scatter(
        x=comparativo["media_capitais"], y=comparativo["funcao"], mode="markers",
        marker=dict(color="black", symbol="line-ns", size=14, line_width=2),
        name="Média das capitais",
    )
    fig_exec.update_layout(height=750)
    col1.plotly_chart(fig_exec, use_container_width=True)

    fig_diff = px.bar(
        comparativo.sort_values("diferenca"), x="diferenca", y="funcao", orientation="h",
        color="diferenca", color_continuous_scale=["red", "lightgray", "green"], color_continuous_midpoint=0,
        labels={"diferenca": "Diferença vs. média (p.p.)", "funcao": ""},
        title=f"{nome_curto} vs. média das capitais — diferença (p.p.)",
    )
    fig_diff.update_layout(height=750, coloraxis_showscale=False)
    col2.plotly_chart(fig_diff, use_container_width=True)

    st.subheader("Detalhamento por subfunção")
    funcao_detalhe = st.selectbox("Escolha uma função para ver as subfunções", funcoes_disponiveis)

    df_subfuncao = con.execute("""
        SELECT subfuncao, "Coluna" AS estagio, SUM("Valor") AS valor
        FROM despesas
        WHERE "Instituição" = ? AND funcao = ? AND ano = ? AND tipo_conta = 'subfuncao'
          AND "Coluna" IN ('Despesas Empenhadas', 'Despesas Pagas')
        GROUP BY subfuncao, "Coluna"
    """, [capital_selecionada, funcao_detalhe, ano_selecionado]).df()

    if df_subfuncao.empty:
        st.warning("Sem dados de subfunção para essa combinação de capital/função/ano.")
    else:
        pivot_sub = df_subfuncao.pivot(index="subfuncao", columns="estagio", values="valor").reset_index()
        pivot_sub["taxa_execucao_pct"] = round(
            100 * pivot_sub.get("Despesas Pagas", 0) / pivot_sub.get("Despesas Empenhadas", pd.NA), 1
        )
        st.dataframe(pivot_sub, hide_index=True, use_container_width=True)

# ABA 3 — PER CAPITA
with tab_percapita:
    st.subheader(f"Gasto per capita (Despesas Pagas) — {ano_selecionado}")

    funcoes_percapita = st.multiselect(
        "Funções para comparar", funcoes_disponiveis,
        default=[f for f in ["10 - Saúde", "12 - Educação"] if f in funcoes_disponiveis],
    )

    if funcoes_percapita:
        placeholders = ",".join(["?"] * len(funcoes_percapita))
        df_pc = con.execute(f"""
            SELECT "Instituição" AS capital, funcao, MAX("População") AS populacao, SUM("Valor") AS valor_pago
            FROM despesas
            WHERE tipo_conta = 'funcao' AND ano = ? AND "Coluna" = 'Despesas Pagas'
              AND funcao IN ({placeholders})
            GROUP BY capital, funcao
        """, [ano_selecionado, *funcoes_percapita]).df()
        df_pc["per_capita"] = df_pc["valor_pago"] / df_pc["populacao"]
        df_pc["destaque"] = df_pc["capital"].apply(
            lambda x: "Selecionada" if x == capital_selecionada else "Outras capitais"
        )

        cols = st.columns(len(funcoes_percapita))
        for col, funcao_nome in zip(cols, funcoes_percapita):
            dados = df_pc[df_pc["funcao"] == funcao_nome].sort_values("per_capita")
            posicao = dados.reset_index(drop=True)
            posicao_capital = posicao[posicao["capital"] == capital_selecionada].index
            rank_texto = f"{posicao_capital[0] + 1}º de {len(posicao)}" if len(posicao_capital) else "N/D"

            fig = px.bar(
                dados, x="per_capita", y="capital", orientation="h", color="destaque",
                color_discrete_map={"Selecionada": "crimson", "Outras capitais": "lightslategray"},
                category_orders={"capital": dados["capital"].tolist()},
                title=f"{funcao_nome}  (posição: {rank_texto})",
                labels={"per_capita": "R$/habitante", "capital": ""},
            )
            fig.update_layout(height=800, showlegend=False)
            col.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("Selecione ao menos uma função para visualizar.")

# ABA 4 — Estrutura do gasto (Administração e Restos a Pagar)
with tab_estrutura:
    st.subheader(f"Composição do gasto total — {nome_curto}, {ano_selecionado}")

    df_composicao = con.execute("""
        SELECT funcao, SUM("Valor") AS valor
        FROM despesas
        WHERE tipo_conta = 'funcao' AND ano = ? AND "Instituição" = ? AND "Coluna" = 'Despesas Pagas'
        GROUP BY funcao
        ORDER BY valor DESC
    """, [ano_selecionado, capital_selecionada]).df()

    col1, col2 = st.columns(2)

    fig_rosca = px.pie(
        df_composicao, names="funcao", values="valor", hole=0.45,
        title=f"Por função — {nome_curto}",
    )
    fig_rosca.update_traces(textposition="inside", textinfo="percent+label", showlegend=False)
    fig_rosca.update_layout(height=550)
    col1.plotly_chart(fig_rosca, use_container_width=True)

    df_sunburst = con.execute("""
        SELECT funcao, subfuncao, SUM("Valor") AS valor
        FROM despesas
        WHERE tipo_conta = 'subfuncao' AND ano = ? AND "Instituição" = ? AND "Coluna" = 'Despesas Pagas'
        GROUP BY funcao, subfuncao
        HAVING SUM("Valor") > 0
    """, [ano_selecionado, capital_selecionada]).df()

    fig_treemap = px.treemap(
        df_sunburst, path=[px.Constant(nome_curto), "funcao", "subfuncao"], values="valor",
        title=f"Função → Subfunção — {nome_curto}",
    )
    fig_treemap.update_traces(textinfo="label+percent parent")
    fig_treemap.update_layout(height=550, margin=dict(t=50, l=10, r=10, b=10))
    col2.plotly_chart(fig_treemap, use_container_width=True)

    st.divider()
    st.subheader(f"Peso de uma função no orçamento — todas as capitais, {ano_selecionado}")

    col_f, col_c = st.columns([2, 2])
    funcao_peso = col_f.selectbox(
        "Função a analisar", funcoes_disponiveis,
        index=funcoes_disponiveis.index("04 - Administração") if "04 - Administração" in funcoes_disponiveis else 0,
        key="funcao_peso",
    )
    capital_comparar = col_c.selectbox(
        "Comparar diretamente com (opcional)",
        ["Nenhuma"] + [c for c in capitais_disponiveis if c != capital_selecionada],
        key="capital_comparar",
    )

    query_peso_funcao = """
        WITH gasto AS (
            SELECT "Instituição" AS capital, funcao, SUM("Valor") AS total_pago
            FROM despesas WHERE tipo_conta = 'funcao' AND ano = ? AND "Coluna" = 'Despesas Pagas'
            GROUP BY capital, funcao
        ),
        total AS (SELECT capital, SUM(total_pago) AS total_geral FROM gasto GROUP BY capital)
        SELECT g.capital, ROUND(100.0 * g.total_pago / t.total_geral, 2) AS pct_funcao
        FROM gasto g JOIN total t ON g.capital = t.capital
        WHERE g.funcao = ?
        ORDER BY pct_funcao DESC
    """
    df_peso_rank = con.execute(query_peso_funcao, [ano_selecionado, funcao_peso]).df()

    def classificar(capital):
        if capital == capital_selecionada:
            return "Selecionada"
        if capital == capital_comparar:
            return "Comparação"
        return "Outras capitais"

    df_peso_rank["destaque"] = df_peso_rank["capital"].apply(classificar)
    media_peso = df_peso_rank["pct_funcao"].mean()

    fig_peso_rank = px.bar(
        df_peso_rank, x="pct_funcao", y="capital", orientation="h", color="destaque",
        color_discrete_map={"Selecionada": "crimson", "Comparação": "royalblue", "Outras capitais": "lightslategray"},
        category_orders={"capital": df_peso_rank.sort_values("pct_funcao", ascending=False)["capital"].tolist()},
        labels={"pct_funcao": "% do gasto total", "capital": ""},
        title=f"{funcao_peso} — % do orçamento total, todas as capitais",
    )
    fig_peso_rank.add_vline(x=media_peso, line_dash="dash", line_color="gray",
                             annotation_text=f"Média: {media_peso:.1f}%")
    fig_peso_rank.update_layout(height=800, showlegend=True)
    st.plotly_chart(fig_peso_rank, use_container_width=True)

    if capital_comparar != "Nenhuma":
        valor_sel = df_peso_rank.loc[df_peso_rank["capital"] == capital_selecionada, "pct_funcao"]
        valor_comp = df_peso_rank.loc[df_peso_rank["capital"] == capital_comparar, "pct_funcao"]
        if len(valor_sel) and len(valor_comp):
            diff = valor_sel.values[0] - valor_comp.values[0]
            nome_comp_curto = capital_comparar.replace("Prefeitura Municipal de ", "")
            if diff > 0:
                st.info(f"📌 **{nome_curto}** destina **{diff:.1f} pontos percentuais a mais** que **{nome_comp_curto}** para {funcao_peso}.")
            elif diff < 0:
                st.info(f"📌 **{nome_curto}** destina **{abs(diff):.1f} pontos percentuais a menos** que **{nome_comp_curto}** para {funcao_peso}.")
            else:
                st.info(f"📌 **{nome_curto}** e **{nome_comp_curto}** destinam a mesma proporção a {funcao_peso}.")

    st.caption(
        "⚠️ A variação entre capitais pode refletir, em parte, diferenças na "
        "forma como cada prefeitura classifica contabilmente seus gastos "
        "(ex.: alocar TI/RH em Administração vs. distribuir nas funções "
        "finalísticas), não apenas diferenças reais de eficiência."
    )

    st.divider()

    st.subheader(f"Restos a pagar não processados — {ano_selecionado}")
    limite_minimo = st.slider(
        "Valor mínimo empenhado para incluir no ranking (R$)", 0, 5_000_000, 1_000_000, step=100_000
    )

    query_restos = """
        WITH base AS (
            SELECT "Instituição" AS capital, funcao, "Coluna" AS estagio, SUM("Valor") AS valor
            FROM despesas
            WHERE tipo_conta = 'funcao' AND ano = ?
              AND "Coluna" IN ('Despesas Empenhadas', 'Inscrição de Restos a Pagar Não Processados')
            GROUP BY 1, 2, 3
        )
        SELECT
            capital, funcao,
            MAX(CASE WHEN estagio = 'Despesas Empenhadas' THEN valor END) AS empenhado,
            MAX(CASE WHEN estagio = 'Inscrição de Restos a Pagar Não Processados' THEN valor END) AS restos_nao_processados,
            ROUND(100.0 * MAX(CASE WHEN estagio = 'Inscrição de Restos a Pagar Não Processados' THEN valor END)
                  / NULLIF(MAX(CASE WHEN estagio = 'Despesas Empenhadas' THEN valor END), 0), 1) AS pct_travado
        FROM base GROUP BY capital, funcao
        HAVING MAX(CASE WHEN estagio = 'Despesas Empenhadas' THEN valor END) >= ?
        ORDER BY pct_travado DESC LIMIT 20
    """
    df_restos = con.execute(query_restos, [ano_selecionado, limite_minimo]).df().dropna(subset=["pct_travado"])
    st.dataframe(df_restos, hide_index=True, use_container_width=True)

# ABA 5 — Evolução temporal
with tab_padrao:
    st.subheader(f"Taxa de execução média × variação entre capitais — {ano_selecionado}")
    st.caption(
        "Cada ponto é uma função. Eixo X: taxa média de execução entre as 26 "
        "capitais. Eixo Y: o quanto essa taxa varia de capital para capital "
        "(desvio-padrão). Funções no canto superior esquerdo têm execução baixa "
        "*e* desigual entre capitais; no canto inferior direito, execução alta "
        "e consistente."
    )

    n_minimo_capitais = st.slider(
        "Mínimo de capitais com dado na função (amostra confiável)", 1, 26, 15, key="n_minimo_padrao"
    )

    query_padrao = """
        WITH base AS (
            SELECT "Instituição" AS capital, funcao, "Coluna" AS estagio, SUM("Valor") AS valor
            FROM despesas
            WHERE tipo_conta = 'funcao' AND ano = ?
              AND "Coluna" IN ('Despesas Empenhadas', 'Despesas Pagas')
            GROUP BY 1, 2, 3
        ),
        execucao AS (
            SELECT capital, funcao,
                100.0 * MAX(CASE WHEN estagio = 'Despesas Pagas' THEN valor END)
                      / NULLIF(MAX(CASE WHEN estagio = 'Despesas Empenhadas' THEN valor END), 0) AS taxa_execucao_pct
            FROM base GROUP BY capital, funcao
        )
        SELECT
            funcao,
            COUNT(*) AS n_capitais,
            ROUND(AVG(taxa_execucao_pct), 1) AS taxa_media,
            ROUND(STDDEV(taxa_execucao_pct), 1) AS desvio_padrao
        FROM execucao
        WHERE taxa_execucao_pct IS NOT NULL
        GROUP BY funcao
    """
    df_padrao = con.execute(query_padrao, [ano_selecionado]).df()
    df_padrao_filtrado = df_padrao[df_padrao["n_capitais"] >= n_minimo_capitais]

    fig_padrao = px.scatter(
        df_padrao_filtrado, x="taxa_media", y="desvio_padrao", text="funcao", size="n_capitais",
        color="taxa_media", color_continuous_scale="RdYlGn",
        labels={"taxa_media": "Taxa de execução média (%)", "desvio_padrao": "Desvio-padrão entre capitais (p.p.)"},
    )
    fig_padrao.update_traces(textposition="top center")
    fig_padrao.update_layout(height=650)
    st.plotly_chart(fig_padrao, use_container_width=True)

    st.caption(
        f"⚠️ Funções com menos de {n_minimo_capitais} capitais na amostra foram "
        "excluídas por baixa representatividade estatística."
    )

with tab_temporal:
    st.subheader(f"Evolução — {nome_curto} vs. média das capitais (2020-2024)")

    funcao_temporal = st.selectbox(
        "Função para acompanhar ao longo do tempo", funcoes_disponiveis,
        index=funcoes_disponiveis.index("10 - Saúde") if "10 - Saúde" in funcoes_disponiveis else 0,
        key="funcao_temporal",
    )

    df_evol = con.execute("""
        SELECT ano, "Instituição" AS capital, MAX("População") AS populacao, SUM("Valor") AS valor_pago
        FROM despesas
        WHERE tipo_conta = 'funcao' AND ano BETWEEN 2020 AND 2024
          AND "Coluna" = 'Despesas Pagas' AND funcao = ?
        GROUP BY ano, capital
    """, [funcao_temporal]).df()
    df_evol["per_capita"] = df_evol["valor_pago"] / df_evol["populacao"]

    media_anual = df_evol.groupby("ano")["per_capita"].mean().reset_index().assign(capital="Média das capitais")
    capital_anual = df_evol[df_evol["capital"] == capital_selecionada][["ano", "per_capita", "capital"]]
    df_comp = pd.concat([media_anual, capital_anual], ignore_index=True).sort_values(["capital", "ano"])

    col1, col2 = st.columns(2)
    fig_evol = px.line(
        df_comp, x="ano", y="per_capita", color="capital", markers=True,
        color_discrete_map={capital_selecionada: "crimson", "Média das capitais": "lightslategray"},
        labels={"per_capita": "R$/habitante", "ano": "Ano", "capital": ""},
        title=f"Per capita — {funcao_temporal}",
    )
    col1.plotly_chart(fig_evol, use_container_width=True)

    st.subheader(f"Taxa de execução — {funcao_temporal} — {nome_curto}, 2020-2024")
    df_exec_temporal = con.execute("""
        WITH base AS (
            SELECT ano, "Coluna" AS estagio, SUM("Valor") AS valor
            FROM despesas
            WHERE tipo_conta = 'funcao' AND funcao = ? AND ano BETWEEN 2020 AND 2024
              AND "Instituição" = ? AND "Coluna" IN ('Despesas Empenhadas', 'Despesas Pagas')
            GROUP BY 1, 2
        )
        SELECT ano,
            ROUND(100.0 * MAX(CASE WHEN estagio = 'Despesas Pagas' THEN valor END)
                  / NULLIF(MAX(CASE WHEN estagio = 'Despesas Empenhadas' THEN valor END), 0), 1) AS taxa_execucao_pct
        FROM base GROUP BY ano ORDER BY ano
    """, [funcao_temporal, capital_selecionada]).df()

    fig_exec_temporal = px.line(
        df_exec_temporal, x="ano", y="taxa_execucao_pct", markers=True,
        labels={"taxa_execucao_pct": "Taxa de execução (%)", "ano": "Ano"},
    )
    fig_exec_temporal.update_traces(line_color="crimson", line_width=3, marker_size=10)
    fig_exec_temporal.update_layout(yaxis_range=[0, 105])
    col2.plotly_chart(fig_exec_temporal, use_container_width=True)

    st.subheader(f"Peso de {funcao_temporal} no orçamento — {nome_curto} vs. média, 2020-2024")

    df_peso_temporal = con.execute("""
        WITH gasto AS (
            SELECT "Instituição" AS capital, ano, funcao, SUM("Valor") AS total_pago
            FROM despesas WHERE tipo_conta = 'funcao' AND ano BETWEEN 2020 AND 2024 AND "Coluna" = 'Despesas Pagas'
            GROUP BY capital, ano, funcao
        ),
        total AS (SELECT capital, ano, SUM(total_pago) AS total_geral FROM gasto GROUP BY capital, ano)
        SELECT g.capital, g.ano, ROUND(100.0 * g.total_pago / t.total_geral, 2) AS pct_funcao
        FROM gasto g JOIN total t ON g.capital = t.capital AND g.ano = t.ano
        WHERE g.funcao = ?
    """, [funcao_temporal]).df()

    media_peso_anual = df_peso_temporal.groupby("ano")["pct_funcao"].mean().reset_index().assign(capital="Média das capitais")
    capital_peso_anual = df_peso_temporal[df_peso_temporal["capital"] == capital_selecionada][["ano", "pct_funcao", "capital"]]
    df_peso_comp = pd.concat([media_peso_anual, capital_peso_anual], ignore_index=True).sort_values(["capital", "ano"])

    fig_peso_temporal = px.line(
        df_peso_comp, x="ano", y="pct_funcao", color="capital", markers=True,
        color_discrete_map={capital_selecionada: "crimson", "Média das capitais": "lightslategray"},
        labels={"pct_funcao": "% do gasto total", "ano": "Ano", "capital": ""},
    )
    st.plotly_chart(fig_peso_temporal, use_container_width=True)
    st.caption(
        "Se a linha da capital selecionada ficar sempre acima (ou sempre abaixo) "
        "da média em todos os anos, é um padrão estrutural persistente — não uma "
        "anomalia de um único ano."
    )
with tab_maceio:
    st.subheader("Principais achados sobre Maceió (2024, salvo indicação contrária)")

    col1, col2, col3 = st.columns(3)
    col1.metric("Execução — Habitação", "30%", "-55 p.p. vs. média", delta_color="inverse")
    col2.metric("Per capita — Educação", "R$ 715,71", "25ª de 26 capitais", delta_color="inverse")
    col3.metric("Peso da Administração", "15,19%", "+5,7 p.p. vs. média", delta_color="inverse")

    st.subheader("Raio-x — Maceió vs. média das capitais (100 = igual à média)")

    funcoes_problema = ["16 - Habitação", "06 - Segurança Pública", "14 - Direitos da Cidadania",
                         "15 - Urbanismo", "12 - Educação"]
    query_radar = """
        WITH base AS (
            SELECT "Instituição" AS capital, funcao, "Coluna" AS estagio, SUM("Valor") AS valor
            FROM despesas
            WHERE tipo_conta = 'funcao' AND ano = 2024 AND funcao IN ({})
              AND "Coluna" IN ('Despesas Empenhadas', 'Despesas Pagas')
            GROUP BY 1, 2, 3
        )
        SELECT capital, funcao,
            100.0 * MAX(CASE WHEN estagio = 'Despesas Pagas' THEN valor END)
                  / NULLIF(MAX(CASE WHEN estagio = 'Despesas Empenhadas' THEN valor END), 0) AS taxa_execucao_pct
        FROM base GROUP BY capital, funcao
    """.format(",".join(f"'{f}'" for f in funcoes_problema))

    df_radar_base = con.execute(query_radar).df().dropna(subset=["taxa_execucao_pct"])
    media_radar = df_radar_base.groupby("funcao")["taxa_execucao_pct"].mean()
    maceio_radar = df_radar_base[df_radar_base["capital"] == MACEIO].set_index("funcao")["taxa_execucao_pct"]

    df_radar = pd.DataFrame({
        "funcao": funcoes_problema,
        "Maceió": [100 * maceio_radar.get(f, 0) / media_radar.get(f, 1) for f in funcoes_problema],
        "Média das capitais": [100 for _ in funcoes_problema],
    })
    df_radar_plot = df_radar.melt(id_vars="funcao", var_name="serie", value_name="indice")

    fig_radar = px.line_polar(
        df_radar_plot, r="indice", theta="funcao", color="serie", line_close=True,
        color_discrete_map={"Maceió": "crimson", "Média das capitais": "lightslategray"},
        title="Taxa de execução — índice relativo à média (100 = média das capitais)",
    )
    fig_radar.update_traces(fill="toself", opacity=0.4)
    fig_radar.update_layout(height=550)
    st.plotly_chart(fig_radar, use_container_width=True)
    st.caption(
        "Quanto mais a área vermelha (Maceió) fica *dentro* da área cinza (média = "
        "100), pior a execução relativa de Maceió naquela função."
    )

    st.markdown("""
    - **Habitação — imprevisibilidade, não recorrência.** A taxa de execução oscilou
      de forma extrema entre 2020-2024 (30% → 0% → 99,4% → 86,2% → 30%), sugerindo
      dependência de projetos/contratos pontuais, não um problema estrutural contínuo.
    - **Educação — orçamento per capita consistentemente baixo.** Ao contrário de
      Habitação, o gap frente à média das capitais é persistente ao longo do tempo
      (entre -38% e -49% em 2020-2024), embora venha diminuindo.
    - **Administração — padrão estrutural persistente.** Diferente de Habitação,
      o peso de Administração no orçamento está sempre acima da média das capitais,
      em todos os 5 anos analisados, sem exceção.
    - **Restos a pagar.** Maceió aparece em 3 funções distintas (Habitação, Segurança
      Pública, Direitos da Cidadania) entre os maiores percentuais de valores
      empenhados que sequer chegaram a ser liquidados em 2024.

    Ver o notebook `notebooks/analise_exploratoria.ipynb` para o raciocínio completo,
    incluindo verificações de integridade dos dados (cascata função/subfunção,
    despesas intraorçamentárias, completude por ano).
    """)

    st.warning(
        "Estes indicadores apontam padrões que merecem investigação mais aprofundada — "
        "não são conclusões definitivas sobre eficiência ou desperdício, já que fatores "
        "como qualidade do serviço e contexto local não estão presentes neste dataset."
    )
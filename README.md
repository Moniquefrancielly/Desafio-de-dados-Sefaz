# 🧩 Desafio Técnico — Estágio em Análise de Dados | Sefaz Maceió

Análise das despesas por função das 26 capitais brasileiras (2020–2025), a partir
dos dados do FINBRA/Siconfi, com foco em comparar o que foi **empenhado** com o
que foi **efetivamente pago**, e posicionar Maceió em relação às demais capitais.

## Estrutura do repositório

```
├── dados_compactos/        # .zip originais do FINBRA (fornecidos no desafio)
├── data/
│   ├── interim/             # CSVs extraídos (gerado localmente, não versionado)
│   └── processed/           # finbra.parquet (dataset final, versionado)
├── src/
│   ├── extract.py           # Passo 1 — descompactação automatizada
│   ├── transform.py         # Passo 2 — limpeza, cascata função/subfunção, parquet
│   ├── database.py          # Passo 3 — consultas via DuckDB sobre o parquet
│   └── run_pipeline.py      # Orquestra extract → transform → database
├── notebooks/
│   └── analise_exploratoria.ipynb   # Análise completa, com gráficos e conclusões
├── requirements.txt
└── README.md
```

## Como rodar

```bash
python -m venv venv
venv\Scripts\Activate.ps1        # Windows (PowerShell)
# source venv/bin/activate       # Mac/Linux

pip install -r requirements.txt

python src/run_pipeline.py       # extrai, consolida e valida o pipeline completo
```

Depois, abra `notebooks/analise_exploratoria.ipynb` no VS Code ou Jupyter,
selecionando o interpretador do `venv` como kernel.

## Tratamento dos dados

O formato do CSV do Siconfi tem algumas particularidades tratadas em `transform.py`:

- **Encoding** `latin-1` (não UTF-8), pra não quebrar acentuação.
- **Separador** `;` e **decimal** `,` (padrão brasileiro).
- **3 linhas de metadados** ignoradas (`skiprows=3`) antes do cabeçalho real.
- **Completude por ano**: o pipeline conta quantas capitais aparecem em cada ano
  e imprime o resultado — 2020 a 2024 têm as 26 capitais completas; **2025 tem
  apenas 11**, e por isso foi excluído das comparações e séries temporais
  principais da análise.

### Cascata função → subfunção

A coluna `Conta` mistura funções (`10 - Saúde`) e subfunções (`10.301 - Atenção
Básica`) no mesmo campo. Como a subfunção é matricial (a mesma subfunção pode
aparecer em várias funções diferentes — ex.: `122 - Administração Geral` repete
em `04.122`, `10.122`, `12.122`...), a separação foi feita por **código**, não
por texto, e o resultado mantém o nome completo em cada nível:

- `funcao`: sempre preenchida, com nome completo (ex.: `"10 - Saúde"`).
- `subfuncao`: preenchida apenas quando a linha é uma subfunção (ex.:
  `"10.301 - Atenção Básica"`), permitindo tanto a análise agregada por função
  quanto o detalhamento por subfunção quando necessário.

## Por que Parquet + DuckDB

O dataset consolidado (2020–2025, 6 arquivos CSV) soma ~50 mil linhas — pequeno
o bastante pra caber em memória, mas ler e re-parsear 6 CSVs a cada execução é
lento e repetitivo. Optei por salvar o resultado consolidado em **Parquet**
(formato colunar, comprimido) e consultá-lo com **DuckDB**, que lê arquivos
Parquet diretamente do disco sem precisar de servidor de banco de dados:

```python
con.execute("CREATE VIEW despesas AS SELECT * FROM read_parquet('finbra.parquet')")
```

Isso mantém o projeto leve e portátil — sem infraestrutura pesada — e permite
consultas analíticas complexas (agregações, comparações entre grupos) com SQL,
sem precisar "injetar" os dados numa tabela separada.

## Principais achados

A análise completa, com todos os gráficos e o raciocínio célula a célula, está
em `notebooks/analise_exploratoria.ipynb`. Resumo dos achados sobre Maceió:

| Indicador | Achado |
|---|---|
| **Taxa de execução — Habitação** | 30% (pior colocação entre todas as combinações capital-função do estudo; média das capitais: 85%) |
| **Restos a pagar não processados — Habitação** | 70% do valor empenhado nem chegou a ser liquidado, reforçando que o problema está concentrado num projeto/contrato específico, não disperso |
| **Per capita — Educação** | R$ 715,71/habitante em 2024, 2ª menor entre as 26 capitais; gap frente à média oscilou entre -38% e -49% ao longo de 2020–2024 |
| **Per capita — Saúde** | Posição mediana (13ª de 26); gap frente à média oscilou, chegando a ficar acima da média em 2023 |
| **Peso da Administração no orçamento** | 15,19% do gasto total, 5ª maior proporção entre as capitais (média: ~9,9%) |
| **Padrão geral (todas as capitais)** | Funções de investimento/infraestrutura (Habitação, Saneamento, Agricultura) têm menor taxa média de execução **e** maior variação entre capitais; despesas continuadas (Previdência, Legislativa) têm execução alta e consistente |
| **Habitação ao longo do tempo (2020-2024)** | Execução extremamente volátil: 30% → 0% → 99,4% → 86,2% → 30%. Não é um problema crônico e contínuo — cada ano parece depender de um projeto/contrato pontual e independente, com resultado imprevisível |
| **Administração ao longo do tempo (2020-2024)** | Consistentemente acima da média das capitais em todos os 5 anos (diferença de +3,4 a +5,7 p.p., sem exceção) — ao contrário de Habitação, este é um padrão estrutural persistente, não uma anomalia de um único ano |

**Recorrência:** Maceió aparece em 3 funções distintas (Habitação, Segurança
Pública, Direitos da Cidadania) entre os piores percentuais de restos a pagar
não processados — sugerindo um padrão que não está restrito a uma única área.

**Leitura conjunta — dois tipos de problema diferentes:** a análise temporal
revela que Habitação e Administração representam naturezas de problema
distintas. Habitação sofre de **imprevisibilidade de execução** (o problema é
*quando* o dinheiro sai, não *quanto* é destinado — a alocação anual em si
varia bastante, e a execução varia ainda mais). Administração sofre de
**alocação estruturalmente elevada** (o problema é *quanto* é destinado, de
forma consistente ano após ano, a um item que não é finalístico).

## Limitações e ressalvas

- **Escopo dos dados**: este projeto analisa apenas o lado da **despesa**
  pública (FINBRA Anexo I-E). A origem da receita (impostos, transferências,
  dívida) está fora do escopo dos dados disponibilizados no desafio.
- **Taxas de execução acima de 100%** não são erro — ocorrem porque o valor
  "Pago" no ano pode incluir pagamento de restos a pagar de anos anteriores,
  enquanto "Empenhado" reflete só o compromisso feito naquele ano.
- **Peso da Administração**: a grande variação entre capitais (2,5% a 22,5%)
  provavelmente reflete, em parte, diferenças na forma como cada prefeitura
  classifica contabilmente seus gastos (ex.: alocar TI/RH em Administração vs.
  distribuir esses custos nas funções finalísticas), não apenas diferenças
  reais de eficiência de gestão.
- **Série temporal 2020–2021**: coincide com o período agudo da pandemia de
  COVID-19, que pode ter distorcido tanto os valores de Saúde quanto a
  execução orçamentária geral em todas as capitais.
- **Indicadores como sinais, não conclusões definitivas**: os padrões
  identificados apontam áreas que merecem investigação mais aprofundada — não
  são afirmações categóricas sobre eficiência ou desperdício, já que fatores
  como qualidade do serviço prestado e contexto local de cada capital não
  estão presentes neste dataset.

## Autor

Desenvolvido como parte do desafio técnico de estágio em Análise de Dados da
Sefaz Maceió.
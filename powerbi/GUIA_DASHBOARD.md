# Guia de montagem do dashboard no Power BI

Este guia leva os CSVs de `data/processed/` até um relatório de 7 páginas.
Tempo estimado: 2 a 4 horas na primeira montagem.

---

## 1. Preparação (uma vez)

1. **Tema** — Exibição > Temas > Procurar temas > `powerbi/tema_brighton.json`.
2. **Tamanho da página** — Formatar página > Configurações de tela > 16:9 (1280 × 720).
3. **Parâmetro** — Página Inicial > Transformar dados > Gerenciar parâmetros > Novo:
   `PastaDados` (Texto) = caminho completo da pasta `data\processed`.
4. **Consultas** — abra `powerbi/power_query.pq`. Crie uma *Consulta nula* para cada bloco
   (`fnCsv` primeiro), cole no Editor Avançado e renomeie com o nome do comentário.
   Os tipos de cada coluna já estão definidos no arquivo (gerado automaticamente pelo pipeline).
5. **Tabela de medidas** — Página Inicial > Inserir dados > nome `_Medidas` > Carregar.
6. **Modelo** — escolha UMA das opções:
   - **Tabular Editor (recomendado):** Ferramentas Externas > Tabular Editor > C# Script >
     cole `criar_modelo_tabular_editor.csx` > F5 > Ctrl+S. Cria relacionamentos, ~80 medidas
     com pasta, formato e descrição, marca `dim_date` como tabela de datas e esconde as chaves.
   - **Sem ferramentas externas:** crie os relacionamentos listados em `medidas.yaml` na
     Exibição de modelo e cole `medidas_dax_query_view.dax` na *Exibição de consulta DAX*
     (botão "Atualizar modelo"). Formatos precisarão ser aplicados à mão.
7. Oculte a coluna de `_Medidas` criada no passo 5 (ela vira uma "tabela de medidas").

### Modelo estrela

```
dim_season ─┬─< fact_team_match >── dim_team, dim_date
            ├─< fact_standings  >── dim_team
            ├─< fact_fixtures   >── dim_team (adversário), dim_date
            ├─< fact_player_season >─┐
            └─< fact_transfers ──────┴─ dim_player
```

Regra de ouro: **filtre temporada sempre por `dim_season`** (nunca pela coluna `season` das
fatos). As medidas de comparação com a temporada anterior dependem disso.

---

## 2. Elementos comuns a todas as páginas

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ Título da Página (medida)                       [Temporada ▼]  [Casa/Fora ▼] │
│ Subtítulo da Rodada  (… após 7 rodadas • dados até 18/10/2026)               │
├──────────────────────────────────────────────────────────────────────────────┤
│ VISÃO · DESEMPENHO · MOMENTO · ELENCO · CONFRONTOS · TRANSFERÊNCIAS · SOBRE  │
│ …                                                                            │
│ Fonte dos Dados (rodapé, sempre visível)              Última Atualização     │
└──────────────────────────────────────────────────────────────────────────────┘
```

- **Segmentação de temporada**: `dim_season[season_label]`, seleção única, padrão = atual.
  Sincronize em todas as páginas (Exibição > Sincronizar segmentações), exceto Confrontos e Sobre.
- **Navegação**: Inserir > Botões > Navegador > Navegador de páginas.
- **Rodapé obrigatório**: cartão com `[Fonte dos Dados]`. A licença CC BY-SA da Wikipedia
  exige atribuição visível. Ao lado, `[Última Atualização]`.
- **Sem escudo nem logos**: o escudo do clube e a marca da Premier League são marcas
  registradas. Use só o nome do clube e as cores do tema.

---

## 3. Páginas

### Página 1 — Visão Geral

(Números do desenho: Brighton após 7 rodadas de 2026/27, segundo os dados de teste.)

```
┌─────────┬─────────┬─────────┬─────────┬─────────┬──────────────────────────┐
│ Posição │ Pontos  │  V-E-D  │ Saldo   │ Aprov.  │  PRÓXIMO JOGO            │
│ Atual   │         │         │ de Gols │   %     │  Próximo Adversário      │
│  3º     │   16    │ 5-1-1   │  +18    │  76%    │  25/10 às 11:00          │
├─────────┴─────────┴─────────┴─────────┴─────────┼──────────────────────────┤
│  Pontos acumulados: atual x temporada anterior  │  Forma: E V V V V        │
│  eixo: fact_standings[round]                    ├──────────────────────────┤
│                                                 │  Artilheiro              │
│                                                 │  Líder em Assistências   │
├─────────────────────────────────────────────────┴──────────────────────────┤
│  Últimos jogos: data · adversário · mando · placar · intervalo              │
│  cor de fundo do resultado = medida [Cor do Resultado]                      │
└────────────────────────────────────────────────────────────────────────────┘
```

| Visual | Campos |
|---|---|
| Cartões KPI | `[Posição Atual]`, `[Pontos]`, `[Vitórias]`/`[Empates]`/`[Derrotas]`, `[Saldo de Gols]`, `[Aproveitamento %]` |
| Próximo jogo | `[Próximo Adversário]`, `[Próximo Jogo (Brasília)]`. Se `[Resultados Pendentes]` > 0, mostre um aviso discreto |
| Linha | X: `fact_standings[round]` · Y: `[Pontos Acumulados]`, `[Pontos na Mesma Rodada (Temporada Anterior)]` |
| Tabela de jogos | `fact_team_match`: `match_label`, `goals_for`, `goals_against`, `ht_goals_for`, `ht_goals_against` — filtro do visual `is_brighton = Verdadeiro`, Top 6 por `datetime` |

### Página 2 — Desempenho

Perguntas que responde: *onde o time ganha e perde pontos?*

```
┌───────────────────────────────────────┬────────────────────────────────────┐
│ Casa x Fora (colunas agrupadas)       │  1º x 2º tempo (colunas)           │
│ X: venue · Y: Pontos por Jogo,        │  Gols no 1º/2º Tempo, Gols Sofridos│
│ Gols Pró/Contra por Jogo              │  no 1º/2º Tempo                    │
├───────────────────────────────────────┼────────────────────────────────────┤
│ Resultado por situação no intervalo   │  Saldo de gols por jogo (colunas)  │
│ matriz: ht_state x result_label       │  X: match_label · cor = Cor do     │
│ (quantos jogos vencendo viram empate?)│  Saldo de Gols                     │
├───────────────┬───────────────────────┼────────────────────────────────────┤
│ Viradas       │ Pontos ganhos/perdidos│  Chutes (se football-data ligado): │
│               │ após o intervalo      │  Chutes por Jogo, Precisão %,      │
│               │                       │  Domínio de Chutes %               │
└───────────────┴───────────────────────┴────────────────────────────────────┘
```

O placar do intervalo vem do openfootball. Jogos completados pela Wikipedia não têm intervalo;
`[Jogos com Placar do Intervalo]` mostra em quantos jogos as métricas por tempo se baseiam.
Se `sources.football_data` estiver desligado, esconda o bloco de chutes.

### Página 3 — Momento da Temporada

```
┌──────────────────────────────────────────────┬─────────────────────────────┐
│ Evolução da posição (linha, eixo Y invertido)│ Pontos vs temporada anterior│
│ X: fact_standings[round]                     │ (cartão + seta)             │
│ Y: [Posição na Rodada] · min 1, max 20       ├─────────────────────────────┤
│                                              │ Distância p/ 4º · p/ Z4     │
├──────────────────────────────────────────────┼─────────────────────────────┤
│ Pontos nos Últimos 5 · Forma                 │ Dificuldade Próximos 5      │
├──────────────────────────────────────────────┴─────────────────────────────┤
│ Próximos 5 jogos: adversário · mando · data (Brasília) · posição atual do   │
│ adversário · dificuldade (fundo = [Cor da Dificuldade]); filtro next_n 1–5  │
└────────────────────────────────────────────────────────────────────────────┘
```

A **dificuldade** é uma métrica própria (1 a 5) pela posição atual do adversário: 1º–4º = 5,
5º–8º = 4, 9º–12º = 3, 13º–16º = 2, 17º–20º = 1. Explique isso num ícone de informação.

### Página 4 — Elenco & Jogadores

```
┌─────────────────────────────────────────┬──────────────────────────────────┐
│ Ranking G+A (barras empilhadas)         │ Dispersão: jogos x G+A por jogo  │
│ Eixo: dim_player[player_name]           │ X: [Jogos (Jogador)]             │
│ Valores: Gols (Jogador), Assistências   │ Y: [G+A por Jogo] · cor:         │
│                                         │ position_group                   │
├─────────────────────────────────────────┼──────────────────────────────────┤
│ Titularidade por posição (barras)       │ Tabela completa por jogador      │
│ [Titularidade %] por position_group     │ Jogos, Titular, Banco, G, A,     │
│                                         │ G+A/jogo, Amarelos, Vermelhos    │
└─────────────────────────────────────────┴──────────────────────────────────┘
```

Na tabela, use `dim_player[wikipedia_url]` com categoria de dados "URL da Web" para criar um
link para o artigo do jogador. Isso reforça a atribuição da fonte.

### Página 5 — Confrontos

Página sem filtro de temporada: o histórico contra cada adversário nas 5 temporadas.

```
┌────────────────────────────────────────────────────────────────────────────┐
│ Matriz: linhas = opponent, colunas = season_label, valor = [Pontos]        │
│ (formatação condicional em escala de cor)                                  │
├──────────────────────────────────────┬─────────────────────────────────────┤
│ Pontos por Jogo por adversário       │ Gols Pró x Gols Contra por          │
│ (barras ordenadas)                   │ adversário (barras divergentes)     │
└──────────────────────────────────────┴─────────────────────────────────────┘
```

Todos os campos vêm de `fact_team_match` (coluna `opponent`), com as medidas de Resultados.

### Página 6 — Janela de Transferências

```
┌─────────┬─────────┬─────────┬──────────────────┬─────────────────────────┐
│ Gasto   │ Receita │ Saldo   │ Maior Contratação│ Maior Venda             │
├─────────┴─────────┴─────────┴──────────────────┴─────────────────────────┤
│ Gasto x Receita por temporada (colunas agrupadas + linha do saldo)        │
│ X: dim_season[season_label] — esta página NÃO sincroniza a temporada      │
├───────────────────────────────────────┬───────────────────────────────────┤
│ Chegadas (tabela)                     │ Saídas (tabela)                   │
│ jogador · posição · de · valor · tipo │ jogador · para · valor · tipo     │
│ segmentações: window, movement,       │                                   │
│ is_first_team                         │                                   │
├───────────────────────────────────────┴───────────────────────────────────┤
│ Valores Não Divulgados (cartão) · Empréstimos Cedidos · Gasto Médio        │
└───────────────────────────────────────────────────────────────────────────┘
```

Valores em libras (£), como publicados na Wikipedia. Negócios "Não divulgado" ficam fora das
somas, e o cartão `[Valores Não Divulgados]` deixa isso transparente para quem lê.

Narrativa sugerida: o Brighton é conhecido por **comprar barato, valorizar e vender caro**. O
saldo positivo ao longo das temporadas conta essa história em números.

### Página 7 — Histórico & Sobre

- Colunas: `[Pontos por Jogo]` e `[Posição Final]` por `dim_season[season_label]` (sem filtro).
- Tabela de classificação final por temporada: `fact_standings` + `dim_team[team_name]`.
- Caixa de texto **"Sobre o projeto"**: fontes e licenças (texto do `LICENSE-DATA.md`), como
  os dados foram coletados, link do GitHub e a data da última atualização. Recrutador gosta de
  ver metodologia, e a atribuição da Wikipedia fica completa aqui.

---

## 4. Toques finais que fazem diferença no portfólio

- **Dicas de ferramenta personalizadas** (página de tooltip) no gráfico de evolução da posição,
  mostrando o jogo daquela rodada.
- **Indicadores**: um botão alterna "Casa / Fora / Todos" na página de Desempenho.
- **Consistência de cor**: positivo = verde `#5CD6A0`, negativo = vermelho `#FF6B6B`, destaque =
  amarelo `#FFCD00`, Brighton = azul `#4DA3FF`.
- **Atualização**: rode `python -m brighton all` e depois "Atualizar" no Power BI.
- **Divulgação**: exporte para PDF e grave um GIF navegando pelas páginas para o README e o
  LinkedIn. Se publicar o relatório na web, mantenha o rodapé com a fonte dos dados.

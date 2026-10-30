# 🎯 DNZ Intelligence

Motor de metas e comissionamento para times de vendas, orientado a dados.
Trabalho de Conclusão de Curso, MBA em Inteligência Artificial (PUCRS). Autora: Mayara Diniz Francisco.

## O que é (e o que não é)

- **Módulo 1, calibrador de metas:** sugere a meta de cada vendedor com uma **regra explicável**:
  média dos últimos 3 meses cheios × fator do status do mês (cheio ou parcial) = previsão;
  previsão × fator de desafio = meta. O método foi escolhido por **backtest** em base real.
- **Módulo 2, motor de comissionamento:** `Comissão = MRR × coef. canal × coef. senioridade × acelerador`.
- **Simulação retrospectiva de cenários, fechamento do mês e evidências**, na mesma interface.
- **Machine learning:** foi **testado** (Ridge, Random Forest e Gradient Boosting) e **não superou** a regra explicável;
  por isso o produto usa a regra, que o gestor consegue entender. O ML fica como evolução futura.
- É um **MVP acadêmico**: não há login, multiempresa persistente nem integração com CRM.

## Modelo de comissão (validado em ambiente real)

| Canal | Coeficiente | | Senioridade | Coeficiente |
|---|---|---|---|---|
| Inbound CRM | 1.0 | | Júnior | 1.0 |
| Inbound PRM | 1.4 | | Pleno | 1.1 |
| Outbound | 1.6 | | Sênior | 1.2 |

**Acelerador (% de atingimento da meta):**

- abaixo de 80%: não elegível;
- de 80% a 99%: `(% − 30) ÷ 100` (80% → 50% … 99% → 69%);
- de 100% a 140%: `(100 + (% − 100) × 0,5) ÷ 100` (100% → 100% … 140% → 120%);
- acima de 140%: congelado em 120%; a comissão continua crescendo com o MRR.

O código reproduz, linha a linha, a tabela de 80% a 140% fornecida. Percentuais quebrados (ex.: 79,6%) usam
o inteiro abaixo (configurável na aba Parâmetros).

**Exemplo validado:** MRR R$ 15.720 × 1,0 (Inbound CRM) × 1,1 (Pleno) × 1,20 (144% da meta) = **R$ 20.750,40**,
equivalente a **11,00%** do valor contratado em 12 meses (R$ 188.640). A taxa efetiva varia, no modelo, de cerca de
4,2% (Júnior, Inbound CRM, 80%) a 19,2% (Sênior, Outbound, 140% ou mais) do valor contratado.

## Calibrador de metas

- **Status do mês:** Meta Cheia, Meta Parcial ou Rampagem (coluna `observacao`). Meses parciais entregam cerca de metade do MRR.
- **Fatores:** aprendidos do histórico anterior ao mês-alvo; sem dados suficientes, usa 1,0 e 0,5.
- **Faixa de variação:** percentis 10 e 90 do erro histórico (e não um intervalo fixo).
- **Vendedor novo (menos de 3 meses):** o sistema **não calibra**; mostra uma referência inicial de baixa confiança
  (erro típico validado de 71%) e pede revisão manual.
- **Sazonalidade:** não aplicada. A base tem 18 meses e a validação exige 24 ou mais.
- **Canal e senioridade** são lidos mês a mês, porque o vendedor muda de canal e de nível ao longo do tempo.

## Evidências

**Backtest** (base real anonimizada: 188 vendedores, jan/2025 a jun/2026; 1002 previsões;
janela expansível, sem uso de informação futura). WAPE = soma dos erros absolutos ÷ receita real.

| Método | WAPE | Viés | Dentro de ±10% |
|---|---|---|---|
| Regra explicável (meses cheios × fator do status) | 33,6% | 2,4% | 19,3% |
| Gradient Boosting | 33,8% | 7,3% | 18,4% |
| Random Forest | 34,0% | 7,0% | 19,8% |
| Média móvel 3m (só meses cheios) | 37,2% | 5,4% | 18,1% |
| Heurística DNZ (atual) | 37,5% | -5,1% | 15,3% |
| Média móvel 3m | 37,7% | -1,6% | 15,7% |
| Heurística DNZ (só meses cheios) | 38,0% | 1,6% | 16,1% |
| Ingênuo (último mês) | 40,6% | 0,6% | 16,6% |
| Ridge | 45,9% | 0,8% | 13,0% |

A regra explicável erra de 2.3 a 5.3 p.p. a menos que a heurística anterior
(IC 95%, bootstrap por vendedor) e **empata** com Gradient Boosting e Random Forest (diferença não distinguível de ruído).

**Estudo de impacto do novo modelo** (vigente desde nov/2025; crescimento sobre o mesmo mês do ano anterior; estudo interno, dados agregados):

| Canal | YoY antes | YoY depois | Aceleração | Dezembro 2025 vs 2024 |
|---|---|---|---|---|
| Inbound CRM | +33,6% | +56,4% | +22,8 p.p. | +101,3% |
| Inbound PRM | +42,0% | +58,6% | +16,6 p.p. | +93,1% |
| Outbound | +8,1% | +10,2% | +2,1 p.p. | +34,2% |

Estudo observacional, sem grupo de controle: indica associação, não prova causalidade.

## Limitações

- Erro mensal alto em todos os métodos (30% a 46%): o MRR por vendedor é muito volátil.
- Meses de rampagem não são avaliáveis pelo backtest; a referência para vendedor novo é de baixa confiança.
- A base de validação não trazia o valor da meta; o backtest mede a previsão de receita, não o atingimento.
- A empresa de validação tem um time maior que o perfil de PME do produto.

## Como rodar

```
pip install -r requirements.txt
python app.py        # http://localhost:5000
```

Backtest offline (com seus dados): `pip install -r requirements-backtest.txt` e
`python backtest.py --arquivo caminho/historico.xlsx` (ou `--sintetico` para testar).

## Privacidade e dados

- Nenhum dado real da empresa está neste repositório. A demonstração usa **30 vendedores pseudonimizados e valores reescalados por um fator constante** (`reescalar.py`).
- As evidências do site mostram apenas percentuais e variações; receitas absolutas foram omitidas.
- Dados enviados por visitantes ficam só na sessão do visitante, em memória, e são descartados depois de algumas horas.
- O `.gitignore` bloqueia arquivos de dados reais e relatórios do backtest.

## Estrutura

```
app.py            servidor Flask e rotas
engine.py         motor de comissão (configurável)
calibrador.py     módulo 1: regra explicável, faixa, partida a frio
simulacao.py      simulação retrospectiva e varredura do fator de desafio
leitor.py         leitura de Excel/CSV (formato brasileiro)
backtest.py       validação offline (baseline, regra explicável e ML)
reescalar.py      reescalonamento de valores em R$ para demonstração
templates/        interface
data/             demonstração, template Excel e evidências
```

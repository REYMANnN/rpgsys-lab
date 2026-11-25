# rpgsys-lab

Laboratório virtual aberto e reproduzível para projetar e testar chips,
placas e racks de IA. Este repositório contém só o laboratório
(ferramentas, testes, casos de calibração). Os designs ficam fora dele.

## Regras

1. Pré-registro com hash antes de cada rodada (`prereg/`).
2. Todo parâmetro tem rótulo: MEDIDO, PUBLICADO (com link), CALIBRADO, ESTIMADO ou HIPÓTESE.
3. Calibrar antes de prever.
4. Controle positivo e negativo em toda campanha.
5. Simetria com o concorrente.
6. Incerteza explícita (Monte Carlo + sensibilidade).
7. Reprodutibilidade: versão, semente e hash de entrada e saída em cada job.
8. Ataque independente antes de qualquer alerta.
9. Nada se apaga: reprovações ficam registradas.
10. Laboratório separado do projeto.

## Fase 0

O job `jobs/roofline_smoke.py` é um teste de fumaça, não um resultado.
A CI prova que o mesmo job produz o mesmo hash no GitHub Actions e no Modal.

```bash
pip install -r requirements.txt
python -m pytest -q
python run_local.py 42
```

## Fase 1 — base fixa e pré-registro

- `base/` — cargas de referência, parâmetros de tecnologia/custo/operação e
  concorrentes, cada um com rótulo, faixa e fonte. `python -m lab.params`
  lista erros bloqueantes e dívidas de fonte.
- `prereg/C001.yaml` — primeira campanha: existe design de pilha própria com
  vantagem >= 3x em custo E energia por token contra a melhor GPU comprável?
  Travado por hash em `prereg/LOCK.txt`; a CI falha se ele mudar.

## Fase 2 — modelo de decode calibrado

- `lab/decode_model.py` — roofline de cálculo e memória por passo de decode,
  com uma única eficiência de sistema `eta`, aplicada igual a todo hardware.
- `prereg/CAL001.yaml` — regra de calibração travada antes da rodada.
- `results/CAL001.json` — resultado: APROVADO (erros -9,3%, +10,3% e -4,5% no
  ponto cego GB200), eta = 0,181.
- Limite: no mesmo GB200 o software variou 1,8x entre versões; `eta` entra nas
  campanhas como faixa aplicada aos dois lados.
- Sensibilidade registrada: o batch por GPU de P1 e P2 não foi publicado
  (HIPÓTESE 256). P1 não depende dele. O ponto cego P2 só passa se o batch for
  >= ~128 por GPU (128: -17,7%; 64: -44%, reprova).

## Campanha C001 — resultado (25/11/2026)

**Veredito: C — REPROVADO** pelo critério travado em `prereg/C001.yaml`.
Arquivo: `results/C001_mc10000.json` (hash de saída no manifesto).

- Melhor design: 12 pilhas HBM3E com atenção feita junto da memória (AMA),
  pouco cálculo central. Nominal: custo 2,17x / energia 3,72x (W1);
  custo 1,91x / energia 3,27x (W2). Energia passa de 3x; custo não.
- Monte Carlo (10.000 sorteios): 0,26% passam 3x nas duas métricas.
  Mediana: custo 1,29x, energia 2,35x.
- Maior incerteza: tempo de "pensar" do agente entre chamadas (Z), ~64% da
  variância do custo; W por pilha de HBM, ~30% da variância da energia.
- Cenário adverso: 0,92x em custo (o prêmio do base die customizado anula a AMA).
- Controle negativo: a mesma placa sem a lógica junto da memória fica em 0,92x;
  a lógica é o que cria a vantagem. Controle positivo: 1,000.
- Limite de exportação (TPP < 4.800): não muda o melhor design (TPP 1.880).

## MED001 — tempo de espera e tamanho de resposta medidos

`results/MED001.json` (dados: `data/lmcache_timing.parquet`, extraídos de
DiscoPosse/lmcache-agentic-traces por `jobs/extract_med001.py`).

| | Z médio medido | Z assumido na C001 | resposta média medida | assumida |
|---|---|---|---|---|
| W1 código (665 sessões) | 1,99 s | 3,0 s | 212 tokens | 40 |
| W2 pesquisa (94 sessões) | 3,72 s | 5,0 s | 181 tokens | 40 |
| W3 empresa (8 sessões, fraco) | 2,61 s | 20 s | 338 tokens | 40 |

## Correção r1 e campanhas -r1

Ver `CORRECOES.md`. Energia de servidor/rede passou a entrar de forma simétrica.

| campanha | veredito | nominal (min W1/W2) | adverso | Monte Carlo >= 3x |
|---|---|---|---|---|
| C001 (original) | C | 1,91x | 0,92x | 0,26% |
| C001-r1 | C | 1,87x | 0,92x | 0,15% |
| C001b-r1 (Z e resposta medidos) | **B — zona cinza** | **4,78x** | 1,13x | 38,3% |

C001b-r1, melhor design: 12 pilhas HBM4 com atenção no base die (AMA),
200 mm² de cálculo, 2 GB de SRAM. W1: custo 5,14x, energia 8,09x. Dentro do
limite de exportação (TPP < 4.800): 8 pilhas HBM4 + AMA, custo 4,09x,
energia 6,94x. Maior incerteza: Z (54% da variância do custo); preço da HBM4 (17%).
Controle negativo (mesma placa sem AMA): 2,17x — não passa no critério A.

## Lab 2 v0 — FIS001 (térmico da pilha e rack)

`results/FIS001_mc10000.json`. Veredito do finalista: **ZONA CINZA**.
- Pilha HBM com a lógica de atenção no base die, resfriamento líquido:
  96 °C no caso conservador (limite 90 °C com margem), 80 °C no distribuído.
  Monte Carlo: 22% / 56% dos sorteios abaixo de 90 °C.
- Orçamento de lógica por pilha: 29 W (conservador) a 49 W (distribuído);
  o finalista usa 37 W. A ar: reprova (126 °C).
- Teste de plausibilidade (pilha padrão 40 W, líquido): 51–67 °C, dentro da
  faixa publicada. Não é calibração: falta medição.
- Rack: ~34 placas por rack a ar pela potência, mas as pilhas pedem líquido no chip.

## Placar

`python -m jobs.progresso` — hoje: **25,5%** até "engenheiro confirma
fabricável" (pesos e critérios em `gates/engenheiro.yaml`).

## Riscos abertos que o modelo ainda não cobre
- Ligação entre as nossas placas (rede entre chips) entra só como custo, sem
  penalidade de desempenho: favorece a gente. Gate G12.
- Acesso a base die customizado de HBM (hoje só para gigantes): não é custo, é acesso.

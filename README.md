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

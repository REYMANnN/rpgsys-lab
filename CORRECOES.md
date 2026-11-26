# Registro de correções do modelo

| rev | data | o quê | como foi achado | direção | efeito |
|---|---|---|---|---|---|
| r1 | 2026-11-25 | Energia de servidor/rede (CPU, RAM, NIC, ventilação, switch) não entrava para quem não tem preço de rack (nós, MI355X, H200); B300 usava só a potência da GPU apesar do preço de rack | revisão adversarial da C001b, ANTES de qualquer alerta | a favor de nós | ver C001-r1 e C001b-r1 |

Regra: resultados antigos ficam como estão (com hash). Cada correção gera
nova rodada com sufixo -rN, e as duas ficam lado a lado.

Nota de transparência: uma rodada exploratória da C001b com 30 sorteios, feita
antes da r1, deu nota nominal 4,85x. Esse número otimista motivou a revisão
adversarial que achou a assimetria. O arquivo dessa rodada foi descartado por
ser anterior à correção; só valem as rodadas -r1 de 10.000 sorteios.

## C002 (25/11/2026)
- Antes da rodada de 10k houve um teste de 20 sorteios (apagado; declarado no prereg C002L).
- C002 e C002L originais tinham índice de Sobol falso (L7). Re-rodados como -r1; vereditos e números de custo/energia idênticos.

## PI001 (25/11/2026)
- Um teste fora do repositório mostrou queda DC de 19–36%: o modelo não tinha o sensoriamento remoto do VRM (o regulador
  mede a tensão no die e compensa a queda do caminho). Era erro de física do modelo, não de parâmetro. Corrigido
  (linha de carga 0,015–0,030 mΩ, valores ESTIMADOS) e rodado como PI001-r1. Os critérios do prereg não mudaram.

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

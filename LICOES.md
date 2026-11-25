# Lições aprendidas -> verificações permanentes

Cada erro achado vira uma verificação automática que roda em toda CI e
antes de todo veredito. O erro não pode voltar sem a CI ficar vermelha.

| # | erro original | verificação permanente | onde |
|---|---|---|---|
| L1 | número escrito como "100.0e6" lido como texto | validador acusa texto numérico em qualquer parâmetro | `lab/params.py`, `tests/test_base.py` |
| L2 | conclusão dependia de hipótese não publicada (batch por GPU) sem aviso | toda HIPÓTESE usada numa calibração precisa de teste de sensibilidade que trava a faixa em que a conclusão vale | `tests/test_decode_model.py` |
| L3 | código enviado com teste falhando | gancho pre-commit roda os testes; CI bloqueia | `scripts/pre-commit`, CI |
| L4 | custo/energia de infraestrutura aplicado de forma assimétrica | teste de simetria por componente + guarda no juiz | `tests/test_system_model.py`, `lab/guards.py` |
| L5 | arquivo de resultado quase sobrescrito por rodada nova | resultados são imutáveis: gravar em cima falha | `lab/guards.py::salvar_resultado` |
| L6 | resultado otimista visto antes da revisão | guarda de "bom demais" e de impossibilidade física antes de qualquer veredito | `lab/guards.py` |

## L7 — índice de sensibilidade falso para entrada constante (C002, 25/11/2026)
O cálculo de Sobol ordenava pares (x, y); com x constante, a ordem virava a de y e o índice dava ~0,97 para
variáveis que nem variam. Correção: pular entradas constantes/não numéricas e ordenar só por x.
Check permanente: tests/test_sobol.py. Os resultados C002/C002L foram re-rodados como -r1; os originais ficam guardados.

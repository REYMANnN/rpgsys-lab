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

## L8 — cenário adverso assimétrico (C002, 25/11/2026)
No adverso "memória cara", só a nossa HBM encarecia; as GPUs usam a mesma HBM e ficavam com preço de tabela.
Correção (C003): a alta de preço é repassada às GPUs por um fator de repasse (0,25–1,0, nominal 0,5).
Check permanente: tests/test_simetria_memoria.py.

## L9 — tabela (ROM) vira estado livre na prova formal (G10, 25/11/2026)
A tabela da exponencial estava como Array de constantes; o Amaranth/Yosys a trata como memória e, na k-indução,
o conteúdo inicial não é garantido — o solver achou um contraexemplo com a tabela "errada". O hardware simulado
estava certo, mas a prova não valia. Correção: tabela como lógica combinacional (case). Check permanente: a prova
formal roda no CI (formal/ama_formal.py).
## L10 — estouro do acumulador l acima de 65.536 tokens (G10)
l tinha 32 bits; com contexto de 137 mil tokens e escores parecidos, l passa de 2^32. Corrigido para 40 bits e
provado formalmente (P2: l <= tokens x 2^16 < 2^40 para até 16 milhões de tokens).
## L11 — k-indução da pista da AMA não fecha (G10, aberto)
A verificação limitada (BMC) a partir do reset passa; a k-indução (depth 3 e 8) devolve contraexemplos com estados
inalcançáveis cujos sinais intermediários no VCD não batem com a lógica (a tabela isolada foi verificada e está certa).
Hipótese: estado escondido do domínio de clock/reset no RTLIL. Até fechar, o placar conta G10 como parcial.

## L12 — tempo de relógio dentro do resultado quebra a comparação de reprodução (G17)
SW002A reproduziu idêntico em todas as métricas, mas o hash mudou porque o campo "segundos" estava nas saídas.
Correção: reproduzir.py compara o hash das saídas sem campos voláteis (lista VOLATEIS).

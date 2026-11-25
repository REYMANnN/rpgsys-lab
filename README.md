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

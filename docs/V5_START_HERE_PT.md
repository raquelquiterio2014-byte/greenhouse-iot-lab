# Greenhouse IoT Lab V5 — Integração e avaliação

Abra a pasta do projeto no PyCharm. Execute **main.py** para abrir o painel
e **run_v5_evaluation.py** para rodar a avaliação de ponta a ponta. Você também
pode executar pelo terminal do PyCharm:

```powershell
python main.py
python run_v5_evaluation.py
python -m unittest discover -s tests
```

Execute os comandos separadamente. A avaliação inicia e encerra seu próprio
receptor em uma porta local livre. Ela usa bancos temporários, não altera os
dados do painel e não precisa de chave de API. O relatório fica em
`exports/v5_evaluation.json`. Use `--scenario reconnect_heat` para repetir
apenas o cenário de reconexão.

| Cenário | Resultado esperado |
| --- | --- |
| normal | SCREENED: série válida sem alerta configurado |
| reconnect_heat | REVIEW_REQUIRED: a fila é recuperada, a confirmação perdida não duplica a leitura e o calor acima do limite pede revisão |
| stale | BLOCKED: o contato do dispositivo pode estar ativo, mas as medições são antigas |
| sensor_fault | BLOCKED: o dispositivo informa falha no sensor |

No JSON, `passed` indica se as verificações do cenário passaram.
`analysis.status` descreve o resultado da análise: um bloqueio esperado pode
ser um teste bem-sucedido. Veja `gate_reasons` e `findings` para entender
o motivo. O relatório registra a origem sintética e mantém a autorização
como `NO_ACTION_AUTHORIZED`.

Na aba **AI analysis**, os exemplos da V4 continuam disponíveis. O Gemini
permanece opcional. A avaliação da V5 verifica a integração do software com
dados sintéticos; sensores físicos, Wi-Fi do ESP32, interface no Windows e
chamada real ao Gemini ainda precisam ser validados.

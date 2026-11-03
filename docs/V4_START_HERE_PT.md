# V4 — Análise de tendências e revisão assistida por IA

## 1. Abrir e testar agora, sem chave e sem sensores

1. Extraia o ZIP inteiro para uma pasta nova, como `D:\greenhouse-iot-lab-v4`.
2. No PyCharm, abra a pasta que contém `main.py`. Selecione Python com Tcl/Tk (testes feitos em Python 3.12).
3. Execute **main.py**. Não é necessário instalar pacotes do pip.
4. Abra a aba **AI analysis**.
5. Em **Input**, escolha **Rising heat**.
6. Deixe desmarcada a opção de envio ao Gemini.
7. Clique **Analyze snapshot**.
8. Observe o estado **REVIEW_REQUIRED**, os números calculados e as evidências E01, E02 etc.

Essa execução é local e determinística. Ela NÃO é uma resposta do Gemini. O relatório mostra `NOT_REQUESTED / LOCAL_ANALYSIS_ONLY`.

## 2. Exemplos disponíveis

| Input | O que demonstra |
|---|---|
| Current selected source | Usa até 500 registros da origem selecionada no topo: DEMO, HTTP TEST ou LIVE ESP32 |
| Normal example | Nenhum sinal configurado; isso não significa que o cultivo esteja seguro/ótimo |
| Rising heat | Temperatura crescente e acima do limite ilustrativo |
| Dry soil | Queda do índice relativo do solo e cruzamento do limite configurado |
| Temperature spike | Salto da última temperatura contra a mediana anterior |
| Stale readings | Dados antigos: análise e chamada ao modelo bloqueadas |
| Uncalibrated soil | Calibração ausente: análise e chamada ao modelo bloqueadas |
| Saturated light | Luz saturada: análise e chamada ao modelo bloqueadas |

Os exemplos contêm doze observações sintéticas ao longo de 55 segundos. Eles não são acrescentados à tabela de medições e não contaminam a origem física. Os relatórios salvos identificam `synthetic_case` e a origem de demonstração.

Para analisar a simulação que você vê nos cartões, selecione **Current selected source** e mantenha DEMO rodando por pelo menos 20 segundos. São necessários cinco registros válidos e intervalo mínimo de 20 segundos; cinco leituras rápidas, sozinhas, não bastam.

Para o teste HTTP, inicie o dispositivo de teste na aba Connectivity lab e aguarde dados suficientes. Para LIVE ESP32, é necessário receber medições físicas e concluir a calibração do solo. A validação física desta entrega permanece pendente.

## 3. O que a análise local calcula

- Janela recente de 30 minutos, limitada aos últimos 500 registros.
- Média, mínimo, máximo e mudança entre início e fim para cada variável.
- Inclinação de uma regressão linear simples por minuto, como descrição do trecho observado.
- Possível salto da última leitura comparada à mediana das anteriores: limiar maior entre um piso configurado no código e seis vezes a escala robusta de desvio absoluto mediano (MAD × 1,4826).
- Alertas dos limites de temperatura e índice relativo do solo já configurados no aplicativo.

Pisos heurísticos: 2 °C, 8 pontos de umidade relativa do ar, 10 pontos do índice relativo do solo e 500 lux. São exemplos de triagem, não limites agronômicos validados. Os parâmetros e métodos ficam registrados no relatório.

Não há previsão de temperatura futura, modelo de anomalia treinado, diagnóstico de planta ou cálculo de necessidade de irrigação. A inclinação de um trecho curto pode ser grande por minuto e não deve ser extrapolada.

## 4. Quando a análise é recusada

O programa bloqueia a análise e não chama o Gemini quando há dados insuficientes, antigos, inválidos, saturados, sem calibração, incompatíveis com os valores brutos, com timestamp futuro, misturando origens/dispositivos ou com grandes lacunas de tempo. Um heartbeat de falha de sensores também bloqueia a avaliação.

Para tendências, o programa usa a sequência final válida com a mesma revisão de calibração. Não liga trechos através de uma falha ou troca de calibração. Os registros excluídos são contados e o retrato da janela permanece no relatório. Uma inconsistência de proveniência exige revisão; não é removida para fazer o teste passar.

Status:

- **BLOCKED**: análise retida; consulte Gate reasons.
- **SCREENED**: passou pelos testes implementados, sem sinal configurado. Não é aprovação para operação.
- **REVIEW_REQUIRED**: um ou mais sinais de triagem exigem revisão.

Entradas pela origem física sempre exigem revisão humana, mesmo sem sinais. Todos os relatórios mantêm **NO_ACTION_AUTHORIZED**.

## 5. Ativar Gemini de forma opcional

A integração está implementada; não foi feita uma chamada real ao serviço nesta entrega. Para usá-la na sua máquina, você precisará de chave e modelo disponíveis na sua conta Google.

1. Na aba AI analysis, cole sua chave no campo mascarado **Session key**. Ela fica só na memória daquela sessão.
2. Confira o campo **Gemini model**. O nome padrão histórico do projeto é `gemini-2.5-flash`; a disponibilidade muda conforme a conta e o ciclo do modelo. Você pode informar um modelo compatível que esteja disponível na sua conta. O aplicativo não substitui o modelo sozinho.
3. Selecione primeiro um exemplo válido como Rising heat.
4. Marque **Send the selected aggregate summary to Gemini**. Isso habilita o envio externo do resumo estatístico selecionado.
5. Clique **Analyze snapshot**.
6. Confira o campo **Analysis engine** no relatório. Não interprete fallback local como uma resposta real do modelo.

Alternativa pelo terminal PowerShell do PyCharm:

```powershell
$env:GEMINI_API_KEY="SUA_CHAVE_LOCAL"
$env:GEMINI_MODEL="MODELO_DISPONIVEL_NA_SUA_CONTA"
python main.py
```

Use essas linhas apenas no seu computador; não cole uma chave real em mensagens, README ou GitHub. O programa não lê `.env` automaticamente. O campo Session key, se preenchido, prevalece sobre a variável de ambiente. O modelo também pode ser ajustado no campo da janela.

A API externa pode ter custos/limites próprios. O programa não faz chamadas automaticamente a cada atualização do gráfico; cada solicitação depende do botão e da opção marcada. Dados bloqueados não são enviados.

## 6. Qual é o papel da IA nesta V4?

A análise quantitativa e o estado de revisão são locais. O Gemini recebe somente o resumo calculado, a identificação de origem sintética/física, as evidências predefinidas, verificações permitidas e limitações.

Ele pode escolher:

- uma ordem de prioridade de evidências que já existem;
- verificações como conferir posicionamento, calibração, timestamp e condições locais;
- as limitações obrigatórias que devem acompanhar a resposta.

O texto final é montado por modelos de frase locais a partir dessas seleções validadas. Não é um campo livre para inventar diagnóstico ou recomendar dose de água. A lista completa de achados locais continua no relatório, mesmo quando a IA seleciona apenas alguns para priorizar.

Respostas com evidência inexistente, comando de bomba, campos extras ou omissão de limitações são rejeitadas. O Gemini não acessa ferramentas do computador, não muda medições e não altera os limiares/regras de revisão.

## 7. Proveniência do resultado e falhas

- **NOT_REQUESTED**: Gemini não foi solicitado; triagem local.
- **BLOCKED**: condição dos dados impediu a análise e a chamada.
- **GEMINI**: uma seleção estruturada retornou da API e passou pelo validador. Isso não prova correção agronômica.
- **LOCAL_FALLBACK**: houve chave ausente, rede indisponível, quota, erro ou resposta inválida; os resultados locais permanecem identificados.

São no máximo duas tentativas para falhas transitórias, com espera curta entre elas e timeout de 12 segundos por tentativa. Erros como autenticação/modelo inexistente não são repetidos automaticamente. Nenhum corpo de erro com segredo é gravado no relatório.

## 8. Histórico e exportação

**Export JSON** preserva a janela de observações, calibração, hash SHA-256, parâmetros, resultados locais e origem do resultado da IA. **Export text** produz uma versão legível. **Recent run history** lista as execuções da origem atualmente selecionada.

Cada análise adiciona uma linha à tabela `analysis_runs` no SQLite. Não reescreve as medições antigas. O relatório é um retrato com data de corte: se dados novos chegarem, clique novamente para uma nova análise. Ele não permanece válido automaticamente para condições futuras.

A chave e o token do receptor não são exportados. Identificadores de dispositivo/amostra e notas livres de calibração não integram o resumo enviado ao Gemini. O JSON local preserva os registros para estudo. Um hash identifica o conteúdo da janela, mas não é assinatura digital nem banco inviolável.

## 9. Executar sem interface

```console
python analyze_snapshot.py --example "Rising heat"
```

Para solicitar Gemini explicitamente, com chave/modelo no ambiente:

```console
python analyze_snapshot.py --example "Rising heat" --gemini
```

Para analisar dados recebidos e guardados: `python analyze_snapshot.py --source test` ou `--source real`. A regra de qualidade continua sendo aplicada.

## 10. Testes e limites da entrega

Execute `python run_v4_checks.py`. O JSON de teste fica em `exports/v4_software_validation.json`.

Os 78 testes de software incluem respostas simuladas do provedor: eles validam os limites da integração e as alternativas offline. Não houve chamada Gemini real, teste de campo, compilação do ESP32 ou verificação visual no Windows nesta entrega.

Mantenha os guias V2/V3 para os sensores e conectividade. O firmware físico permanece 3.0.0; V4 acrescenta a análise no computador. Bombas e válvulas continuam sem controle físico pelo software. A próxima V5 permanece dedicada à integração final e avaliação.

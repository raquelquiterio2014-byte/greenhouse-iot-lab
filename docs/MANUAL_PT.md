# Greenhouse IoT Lab V2 — Manual de execução e medição

## 1. Abrir no PyCharm

1. Extraia o ZIP inteiro para uma pasta nova, por exemplo `C:\Users\Master\PycharmProjects\Greenhouse_IoT_Lab_V2`.
2. Abra a pasta que contém `main.py` em **File → Open** no PyCharm.
3. Selecione um interpretador Python com Tcl/Tk. As verificações desta versão usam Python 3.12.
4. Execute `main.py` pelo triângulo verde. Não há pacotes pip a instalar.
5. O programa inicia em **DEMO**, com 24,8 °C, 62% RH, 38% relativo e 720 lux sintéticos.

Alternativa: `python main.py`. Se houver erro de Tkinter, teste `python -m tkinter` e confira a instalação do Python/Tcl/Tk.

## 2. O que mudou nas medições

| Tela | Grandeza e unidade corretas | Sensor selecionado |
|---|---|---|
| Air temperature | Temperatura do ar, °C | DHT22 / AM2302 |
| Air relative humidity | Umidade relativa DO AR, % RH | O mesmo DHT22 |
| Soil moisture index | Índice relativo de umidade do solo, % relativo | DFRobot SEN0193 |
| Illuminance | Iluminância, lux | BH1750FVI |

O índice do solo não é umidade volumétrica (VWC). A escala depende da sonda, da terra, da alimentação e da configuração do ADC. Lux não é PAR ou PPFD; o projeto não calcula necessidades fotossintéticas a partir de lux.

Duas diferenças do material foram tratadas explicitamente: o DHT22 tem erro de umidade típico ±2 pontos RH, podendo chegar a ±5 nas condições da ficha consultada; o BH1750 tem faixa dependente do modo. O software usa H-resolution, MTreg 69, `lux = contagem / 1,2`, e sinaliza o teto de 16 bits como saturado. Média e mais casas decimais não certificam exatidão.

## 3. Testar os cenários e o histórico

Em **Overview**, mantenha DEMO e escolha Normal, Dry soil, Hot day, Night ou Light saturation. As amostras sintéticas mudam a cada dois segundos; as referências de calibração da demonstração são separadas das reais.

- **Dry soil**: teste o alerta e a irrigação simulada. Liga abaixo de 35%, para a 45% ou no máximo 20 s.
- **Hot day**: alerta de temperatura.
- **Light saturation**: a contagem do BH1750 chega a 65535. O cartão de lux fica indisponível e o alerta explica a saturação.
- **Pause demo**: congela leituras e para a irrigação simulada.
- **Water 10 s (demo)**: irrigação manual simulada; Stop também desmarca o automático.

Em **History & events**, use a barra horizontal para ver ADC, mV, Quality e Calibration. **Export CSV** grava todas as amostras da origem selecionada, com dados brutos, corrigidos e calibração. Leituras com problema permanecem no histórico para auditoria; não são apagadas para esconder o problema. Uma origem não é somada à outra.

## 4. Especificação e posicionamento

Na aba **Sensors & calibration**, selecione cada grandeza para ler a ficha do sensor e a justificativa.

- **DHT22**: abrigo branco ventilado, altura representativa das folhas, ajustada ao crescimento. Evitar sol direto, respingos, condensação, calor de motor/telhado e correntes diretas de ventilação. Não imergir para calibrar.
- **SEN0193**: lâmina sensora em contato com a região ativa das raízes; topo eletrônico acima do substrato e protegido de água. A profundidade depende do vaso/raiz e do tamanho da lâmina. O exemplo de 15 cm do curso não autoriza enterrar toda a placa. Sondas genéricas v1.2 exigem conferência elétrica própria.
- **BH1750**: horizontal, voltado para cima, pouco acima da folhagem; evitar sombras estruturais. Uma janela de proteção pode alterar a leitura. Sol forte pode saturar o modo escolhido.

Não adicionamos PIR, MQ, ACS712, BME280 ou DS18B20 só por estarem no catálogo da aula. BME280 é uma alternativa se pressão for necessária; DS18B20 é apropriado para uma futura temperatura de líquido com encapsulamento adequado. Eles não estão implementados nesta versão.

## 5. Ligações — ESP32 DevKit clássico

Faça ligações desenergizadas e confira o módulo real. O firmware não foi validado fisicamente.

| Componente | Sinal | ESP32 clássico |
|---|---|---|
| DHT22 | DATA | GPIO 4 |
| SEN0193 | AO | GPIO 34 / ADC1 |
| BH1750 | SDA / SCL | GPIO 21 / 22 |
| Todos | GND | GND comum |
| Sensores compatíveis | VCC | 3V3 nesta montagem |

DHT22 avulso pode exigir pull-up conforme datasheet; alguns módulos já o incluem. SEN0193 especifica alimentação 3,3–5,5 V e saída 0–3 V; nesta montagem é alimentado em 3,3 V. O BH1750 é um módulo compatível com 3,3 V no endereço 0x23. GPIOs do ESP32 não aceitam automaticamente sinais de 5 V.

O firmware fixa 12 bits e atenuação de 11 dB para GPIO34. A faixa útil real depende do chip/configuração. `soil_raw` é média de dez leituras ADC; `soil_mv` é média de outras dez conversões `analogReadMilliVolts()`. Os pares não são a mesma conversão instantânea. O modelo ideal contagem/4095 × 3,3 é apenas didático e não é usado como tensão real.

## 6. Configurar PC e ESP32

1. PC e placa na mesma rede Wi-Fi local; ESP32 clássico usa 2,4 GHz.
2. Na aba **IoT connection & settings**, use Receiver host `0.0.0.0`, porta `8765`, Save settings e Start receiver.
3. Copie o token pelo botão Copy token.
4. Descubra o IPv4 do PC com `ipconfig`. A URL da placa será `http://SEU_IP_LOCAL:8765/api/readings`, nunca `0.0.0.0`.
5. Copie `firmware/greenhouse_esp32/secrets.example.h` como `secrets.h` na mesma pasta, preenchendo Wi-Fi, URL e token. Não envie esse arquivo ao GitHub.
6. Na Arduino IDE, configure a placa ESP32 e instale DHT sensor library / Adafruit Unified Sensor e BH1750 (claws).
7. Abra e envie `greenhouse_esp32.ino`. O firmware agora é V2; não basta manter o sketch V1.
8. Abra monitor serial em 115200 baud. Ele mostra média ADC e mV do solo.
9. No aplicativo, selecione LIVE ESP32. Aguarde a amostra de um minuto.

O receptor usa HTTP local com token, sem TLS. Use rede privada confiável; não exponha porta do roteador à internet. `http://127.0.0.1:8765/health` testa o receptor no próprio PC, não os sensores.

## 7. Calibrar o solo e verificar o ar

Ao receber V2 pela primeira vez, o solo terá `CALIBRATION_REQUIRED`; temperatura, umidade do ar e luz podem ser apresentadas, mas o índice do solo não deve ser utilizado sem as referências.

1. Identifique a sonda, o substrato, a alimentação e o ADC usados. Obtenha uma referência seca e uma úmida adequadas, sem molhar o topo eletrônico. A calibração deve fazer sentido para aquele substrato, não somente para ar e água.
2. Anote as médias brutas do monitor serial ou do histórico. Aguarde estabilização de cada referência.
3. Abra **Sensors & calibration**. Substitua Dry reference e Wet reference.
4. Os exemplos 3000/1200 são números didáticos, não uma calibração pronta. A interface exige referências dentro de 1..4094 e separadas por pelo menos 50 contagens, uma regra de consistência deste protótipo, não especificação do fabricante.
5. Em Probe ID / substrate / reference / operator, registre sonda, terra, condições, responsável e referência de verificação. A data é registrada automaticamente ao salvar.
6. Marque a confirmação somente depois de medir as referências.
7. Preview latest real raw sample mostra o efeito sobre a última contagem recebida, sem mudar o banco.
8. Save calibration revision cria uma nova revisão. Aguarde a próxima amostra real para o painel refletir a nova conversão.

Fórmula: `índice = 0 + (contagem − seco) × 100 / (úmido − seco)`. Funciona com polaridade invertida se as referências estiverem corretas. O programa preserva o valor antes do limite e o valor limitado a 0–100. Se estiver fora das referências, sinaliza e não apresenta o solo como utilizável.

Para o DHT22, verifique contra referência apropriada. O offset é `valor de referência − valor lido`; por exemplo 29,5 − 30,2 = −0,7 °C. Temperatura e umidade têm correções independentes. Limites de configuração: ±5 °C e ±10 pontos RH. Zero significa sem ajuste, não “instrumento certificado”. Nunca coloque o DHT22 em gelo/água fervente: o exemplo da aula se aplica a uma sonda apropriada, não a todo sensor.

## 8. Qualidade e dados antigos

- `OK`: passou pelos testes implementados, sem constituir certificado de exatidão.
- `CALIBRATION_REQUIRED`: faltam referências confirmadas do solo.
- `SOIL_ADC_AT_RAIL`: ADC no extremo 0 ou 4095; investigar montagem/sensor.
- `SOIL_OUTSIDE_CALIBRATION`: valor fora das referências; não confiar no recorte para 0/100 como prova de solo seco/molhado.
- `LIGHT_SATURATED`: BH1750 bruto no teto 65535; o lux calculado não é uma medida válida de luz mais intensa.
- `LEGACY_NO_RAW`: formato V1 sem proveniência bruta; atualizar firmware.
- `STALE`: última medição excede o intervalo definido (180 s padrão).

A revisão e o retrato completo dos parâmetros ficam em cada amostra. Alterar a calibração não altera o passado. Amostras retransmitidas com o mesmo sample_id são deduplicadas, mesmo se a calibração tiver mudado.

O firmware guarda até 32 amostras em RAM enquanto Wi-Fi local/PC/receptor estiver indisponível. Reinício perde a fila e lotação descarta o mais antigo. A idade enviada permite distinguir atraso de dado recente. Uma calibração nova aplica-se a mensagens que chegarem depois, inclusive filas antigas; essa política é registrada no retrato da amostra. Não há relógio metrológico sincronizado na placa.

## 9. Atualizar sem perder V1

Faça cópia de segurança da pasta `data` com o app fechado. Para começar limpo, abra V2 numa pasta nova. Se quiser migrar, copie a `data/greenhouse.sqlite3` antiga e as configurações para V2 antes de abrir. Novas colunas são acrescentadas e registros antigos preservados como legados. Não rode V1 novamente sobre o banco migrado como rotina de trabalho.

Dados locais e `secrets.h` são ignorados pelo Git; upload manual pelo navegador exige excluir esses arquivos por conta própria.

## 10. Critérios de conclusão

- Quatro cartões com unidades e nomes adequados.
- Aba de sensores com ficha de cada grandeza.
- DEMO funciona sem hardware, incluindo saturação de luz.
- LIVE sem calibração não apresenta solo como utilizável.
- Calibração salva cria revisão, aplicada às próximas amostras.
- CSV contém dados brutos, corrigidos, qualidade e retrato de calibração.
- Histórico V1 é preservado e identificado.
- Verificação física posterior confirma pinagem, resposta e referências na estufa.

Teste pelo terminal do PyCharm: `python -m unittest discover -s tests -v`.

Relé e válvula normalmente fechada de 12 V constam apenas como especificação futura. Comando, corrente da carga/partida, fonte separada, proteção e estado em falha precisam de projeto próprio. Nenhum atuador físico está conectado ao software nesta versão.

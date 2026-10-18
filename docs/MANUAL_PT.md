# Manual — Estufa IoT no PyCharm

## 1. O que você vai abrir

O programa é uma janela desktop em Python. A interface está em inglês e contém quatro cartões com valores e gráficos:

| Cartão | Medição | Valor inicial de demonstração |
|---|---|---|
| Air temperature | Temperatura do ar | 24,8 °C |
| Air humidity | Umidade relativa do ar | 62% |
| Soil moisture | Umidade relativa do sensor no solo | 38% |
| Light intensity | Iluminância | 720 lux |

Os valores iniciais são os da imagem do post. No modo DEMO, eles variam para simular a estufa. No modo LIVE ESP32, a tela só apresenta dados recebidos. O projeto não contém uma fotografia dentro do painel: os cartões e gráficos são componentes reais da interface, atualizados pelo programa.

## 2. Abrir e rodar no PyCharm

1. Baixe o ZIP e clique com o botão direito → **Extrair tudo**. Não execute dentro do ZIP.
2. Sugestão de pasta: `C:\Users\Master\PycharmProjects\Greenhouse_IoT_Lab`.
3. No PyCharm: **File → Open** e selecione a pasta que contém `main.py` e `README.md`.
4. Selecione seu interpretador Python. Você pode criar um ambiente virtual pelo próprio PyCharm. O projeto foi verificado com Python 3.12 e não exige pacotes do pip.
5. Abra **main.py**.
6. Clique com o botão direito no arquivo → **Run 'main'**, ou use o triângulo verde.
7. A janela **Greenhouse IoT Lab | Sensor Dashboard** será aberta em modo DEMO.

Alternativa pelo terminal, dentro da pasta do projeto:

```console
python main.py
```

Há também `run_windows.bat`, que depende de o comando `python` estar configurado no Windows. Se não funcionar, use o PyCharm.

Se houver erro de Tkinter, teste `python -m tkinter`. Use uma instalação do Python com Tcl/Tk habilitado. Se aparecer `No module named greenhouse`, confirme que a pasta `greenhouse` está junto de `main.py` e que toda a pasta foi extraída.

## 3. Testar sem comprar sensores

Na aba **Overview**:

1. Confira o botão **DEMO** selecionado.
2. Observe as quatro medições. Uma nova amostra é gerada a cada dois segundos.
3. Em **Demo scenario**, escolha **Dry soil**. O solo começa abaixo de 35%.
4. Com **Auto irrigation (demo)** marcado, a válvula simulada liga. O solo simulado ganha umidade.
5. A simulação para ao atingir 45% ou após no máximo 20 segundos. Se atingir o tempo máximo antes da meta, fica bloqueada até recuperação do solo ou reinício do cenário.
6. Escolha **Hot day** para verificar o alerta de temperatura acima de 38 °C.
7. Escolha **Night** para observar a queda da luminosidade.
8. **Pause demo** congela as leituras e interrompe a irrigação simulada. **Resume demo** retoma as amostras.
9. **Water 10 s (demo)** inicia uma irrigação manual simulada, com limite de dez segundos ou parada antecipada ao atingir 45%.
10. **Stop** interrompe a simulação e desmarca o automático. Marque novamente para reativá-lo.

Os limites são exemplos de estudo e não uma receita agronômica. Não há acionamento de equipamento físico.

## 4. Histórico, eventos e CSV

Na aba **History & events**, a tabela mostra as últimas 120 amostras da origem selecionada. Os gráficos também usam essa janela. Os horários são exibidos no horário local do computador; o banco guarda timestamps com fuso UTC.

**Export CSV** exporta TODO o histórico da origem selecionada, não apenas as 120 linhas visíveis. O CSV inclui `source`, `device_id`, `sample_id`, horário de medição, horário de recebimento e as quatro variáveis. Em Excel configurado para português, use **Dados → De Texto/CSV** e selecione vírgula como delimitador.

O histórico permanece após fechar o aplicativo. Alternar entre DEMO e LIVE muda o conjunto consultado e evita misturar amostras sintéticas e reais. A lista inferior guarda mudanças de alertas e eventos da irrigação simulada.

## 5. Hardware para a etapa real

Para as quatro medições, a implementação proposta usa:

- 1 ESP32 DevKit clássico com USB.
- 1 DHT22 para temperatura e umidade do ar.
- 1 sensor capacitivo analógico de solo compatível com alimentação e saída de 3,3 V.
- 1 BH1750 em módulo compatível com 3,3 V, para lux.
- Protoboard, fios e cabo USB com dados.

Confira o módulo adquirido e seu datasheet. O projeto não inclui controle de bomba; não é necessário comprar relé ou válvula para testar o monitoramento. Não ligue cargas de rede elétrica ao ESP32.

### Ligações propostas — ESP32 clássico

Faça as ligações com a alimentação desconectada e confirme os rótulos dos pinos do SEU módulo.

| Sensor | Pino do sensor | ESP32 clássico |
|---|---|---|
| DHT22 | VCC | 3V3 |
| DHT22 | GND | GND |
| DHT22 | DATA | GPIO 4 |
| Solo capacitivo | VCC | 3V3, se o módulo suportar |
| Solo capacitivo | GND | GND |
| Solo capacitivo | AO | GPIO 34 (ADC1) |
| BH1750 | VCC | 3V3 |
| BH1750 | GND | GND |
| BH1750 | SDA | GPIO 21 |
| BH1750 | SCL | GPIO 22 |

DHT22 avulso geralmente precisa de resistor de pull-up entre DATA e 3V3, conforme seu módulo/datasheet; alguns módulos já o possuem. O ESP32 não deve receber sinal de 5 V em seus GPIOs. GPIO 34 é uma escolha para o ESP32 clássico e não deve ser copiada automaticamente para C3/S3. O BH1750 usa o endereço padrão 0x23 no sketch; confira o pino ADD do módulo.

A leitura de solo é um percentual relativo entre duas referências calibradas. Não corresponde automaticamente a umidade volumétrica do solo. Lux mede iluminância; não equivale diretamente a PAR/PPFD para plantas.

## 6. Preparar a conexão no computador

1. Ligue PC e ESP32 ao mesmo Wi-Fi local. O ESP32 clássico usa Wi-Fi de 2,4 GHz.
2. No programa, abra **IoT connection & settings**.
3. Mude **Receiver host** de `127.0.0.1` para `0.0.0.0`.
4. Deixe **Receiver port** em `8765`.
5. Clique **Save settings** e depois **Start receiver**.
6. Se o Windows perguntar, permita a conexão na sua rede privada. Não abra portas do roteador para a internet.
7. Abra o PowerShell e execute `ipconfig`. Localize o IPv4 do adaptador Wi-Fi utilizado, por exemplo `192.168.1.100`.
8. O endereço usado pelo firmware será `http://192.168.1.100:8765/api/readings`, substituindo pelo SEU IP.
9. Clique **Copy token** no aplicativo. Ele será usado no firmware.

`0.0.0.0` significa ouvir nas interfaces do computador; NÃO é o endereço a colocar no ESP32. Se a rede tiver isolamento de clientes, o ESP32 pode não conseguir alcançar o PC.

Com o receptor ativo, abrir `http://127.0.0.1:8765/health` no navegador do PC retorna um pequeno JSON de status. Isso testa o receptor local, não os sensores físicos.

## 7. Gravar o firmware no ESP32

O painel Python roda no PyCharm. O firmware C++ do ESP32 é uma etapa separada, gravada pela Arduino IDE.

1. Na Arduino IDE, configure o suporte de placas ESP32 da Espressif e selecione a placa/porta correspondentes.
2. Pelo gerenciador de bibliotecas, instale **DHT sensor library** da Adafruit, **Adafruit Unified Sensor** e **BH1750** de Christopher Laws/claws.
3. Abra `firmware/greenhouse_esp32/greenhouse_esp32.ino`.
4. Copie `secrets.example.h` para um arquivo chamado `secrets.h` na mesma pasta. Não renomeie o exemplo; mantenha-o como modelo.
5. Preencha nome/senha do Wi-Fi, URL do PC e token. Nunca publique `secrets.h` no GitHub.
6. Faça a calibração de solo indicada abaixo e ajuste os valores no sketch.
7. Compile e envie para a placa.
8. Abra o monitor serial em **115200 baud**.
9. No painel Python, selecione **LIVE ESP32**.
10. Aguarde a primeira medição e depois a atualização a cada minuto. Os valores deixam de ser os da demonstração e passam a ser os dos sensores.

O firmware não foi compilado nem executado em uma placa nesta entrega. As bibliotecas e a pinagem precisam ser confirmadas no seu hardware. A implementação Python e o receptor HTTP foram testados automaticamente.

### Calibração do solo

1. Com o sensor instalado conforme as instruções do fabricante, anote no monitor serial a leitura `Soil raw` numa referência seca adequada.
2. Repita numa referência úmida adequada ao sensor e ao substrato, sem molhar eletrônica não protegida.
3. Substitua `SOIL_DRY_RAW = 3000` e `SOIL_WET_RAW = 1300` pelos valores medidos. Os números fornecidos são apenas exemplos.
4. As referências precisam ser diferentes. A relação pode variar conforme o sensor.
5. Reenvie o sketch. Documente as condições de calibração.

## 8. Protocolo e comportamento offline

A placa envia `POST /api/readings` com `Content-Type: application/json` e `Authorization: Bearer SEU_TOKEN`. Exemplo de formato, não uma medição real:

```json
{
  "device_id": "greenhouse-01",
  "sample_id": "boot123:1",
  "temperature": 24.8,
  "humidity": 62.0,
  "soil_moisture": 38.0,
  "light_lux": 720.0,
  "sample_age_seconds": 0
}
```

A autenticação usa o token criado localmente. O receptor valida números finitos, faixas e ID de dispositivo. Amostras repetidas com o mesmo `sample_id` não são inseridas novamente. Temperatura aceita -40..80 °C, umidades 0..100% e luz 0..200000 lux: são limites de validação do protótipo, não garantia de precisão dos sensores.

O aplicativo registra a hora de recebimento e estima a hora de medição subtraindo `sample_age_seconds`, calculado pela placa. Isso evita tratar uma fila antiga como se fosse uma leitura fresca, mas não substitui relógios sincronizados e uma validação temporal de produção.

Se internet externa cair, o monitoramento local pode continuar com Wi-Fi local e PC ligados. Se o PC/receptor ou o Wi-Fi local cair, a placa guarda até 32 amostras em RAM e tenta reenviar. Quando a fila lota, descarta a mais antiga. A fila é perdida ao reiniciar ou desligar a placa. Só uma amostra é enviada por tentativa de cinco segundos, permitindo escoar a fila após a reconexão.

O painel mostra **STALE** quando a última medição ultrapassa o limite configurado (180 segundos por padrão). Não inventa valores para preencher a ausência de dados.

## 9. Limites de alerta

Na aba de configuração, ajuste os limites de temperatura, solo e tempo de dado antigo e clique **Save settings**. Eles controlam os alertas de monitoramento. A irrigação de demonstração mantém seus limites didáticos próprios de 35%/45% e máximo de 20 segundos.

Para mudar host/porta com o receptor em funcionamento, clique primeiro **Stop receiver**, altere, salve e reinicie.

## 10. Organização e GitHub

- `main.py`: arquivo para rodar.
- `greenhouse/app.py`: tela desktop.
- `greenhouse/core.py`: dados, histórico, simulação e regras.
- `greenhouse/receiver.py`: receptor HTTP.
- `firmware/`: sketch e exemplo de configurações.
- `tests/`: testes automatizados.
- `data/`: pasta criada ao rodar, com SQLite e configurações locais.

Para testar no terminal do PyCharm, dentro da pasta do projeto:

```console
python -m unittest discover -s tests -v
```

O `.gitignore` exclui dados locais, ambientes virtuais e segredos ao usar Git. Se enviar arquivos manualmente pelo site do GitHub, NÃO selecione a pasta `data`, `.venv`, `__pycache__` nem `secrets.h`.

## 11. Critérios para considerar a primeira etapa concluída

- Janela abre no PyCharm e mostra os quatro cartões.
- Valores e gráficos mudam em DEMO.
- Dry soil e Hot day geram os alertas esperados.
- Irrigação simulada inicia e para; Stop desliga o automático.
- Histórico permanece ao fechar e abrir.
- CSV abre e informa a origem.
- LIVE fica aguardando dados antes da conexão dos sensores.
- Na etapa física, LIVE recebe as quatro medições e acusa dados antigos quando a placa é desconectada.

Esta versão é de monitoramento e estudo. Automação física futura exige projeto próprio para atuadores, proteção elétrica, falhas e validação agronômica.

# V3 — Comece por aqui

## Abrir no PyCharm

1. Extraia o ZIP inteiro em uma pasta nova, como `D:\greenhouse-iot-lab-v3`.
2. Abra essa pasta no PyCharm, selecione o interpretador Python com Tcl/Tk e execute **main.py**.
3. Não é necessário instalar pacotes do pip. Os testes desta entrega usam Python 3.12.
4. O aplicativo começa em **DEMO**, com as quatro grandezas e sem hardware.

## Primeiro teste da V3, sem comprar sensores

1. Abra a aba **Connectivity lab**.
2. Clique **Start test device**. Isso inicia o receptor local, quando possível, e um dispositivo sintético que envia requisições HTTP reais para o receptor.
3. Clique **Show HTTP TEST dashboard**. Os cartões exibem as amostras de teste recebidas pela rede local do computador.
4. Confirme o cabeçalho **HTTP TEST / SYNTHETIC DATA**. Não são medidas da estufa física.
5. Volte para **Connectivity lab** e marque **Pause test link (keep sampling)**.
6. Aguarde cerca de 10 segundos. A fila local cresce enquanto o envio fica pausado.
7. Desmarque a opção. As amostras pendentes são reenviadas; o painel mostra entregas aceitas e eventuais duplicatas.
8. Para testar queda do receptor, clique **Stop receiver**, aguarde alguns segundos e clique **Start receiver**. O dispositivo de teste continua tentando enviar.
9. **Stop test device** interrompe o gerador/envio, preservando a fila de teste em disco para a próxima execução.

O dispositivo sintético usa uma fila persistente de até 32 registros. O firmware ESP32 usa uma fila de 32 registros em RAM; ela NÃO sobrevive ao desligamento. Não confunda os dois comportamentos.

## Como demonstrar medição antiga sem perder o contato

1. Em **IoT settings**, mude **Stale after** para `10` segundos e clique **Save settings**.
2. Em **Connectivity lab**, com o dispositivo sintético rodando, marque **Pause test sampling (keep heartbeat)**.
3. A amostragem para, mas os sinais de presença continuam a cada aproximadamente 30 segundos.
4. Depois de escoar a fila e decorrer o tempo configurado, a medição fica **STALE**. O contato pode permanecer **ACTIVE**: isso é esperado.
5. Desmarque a opção para retomar novas amostras. Depois do teste, volte o limite para `180` segundos se for usar o firmware de amostragem de um minuto.

## O que significam as três origens

| Modo | Caminho | Origem no SQLite/CSV |
|---|---|---|
| DEMO | Gerador direto dentro da interface | `demo` |
| HTTP TEST | Gerador sintético → HTTP → validação → banco | `test` |
| LIVE ESP32 | Entrada destinada à placa e sensores físicos | `real` |

O cliente de teste incluído recusa a URL da origem física e só envia para loopback no endpoint de teste. A calibração sintética é separada da real. Esses rótulos organizam a procedência; não são autenticação criptográfica de um sensor físico. Um cliente externo que possua o token ainda precisa ser identificado e validado pelo operador.

## Diagnósticos

- **Receiver LISTENING/STOPPED**: o receptor deste aplicativo está ou não ouvindo requisições.
- **Contact ACTIVE/SILENT/WAITING**: houve contato autenticado válido nos últimos 90 segundos, contato antigo ou nenhum contato.
- **Measurements FRESH/STALE/NO_DATA**: idade da última medição, independentemente do contato.
- **Sensor heartbeat FAULT/OK/UNKNOWN**: último estado de sensores declarado num heartbeat. Não substitui a inspeção física.
- **Accepted**: nova amostra gravada.
- **Duplicates**: mesmo ID e mesmo conteúdo bruto; reconhecido sem gravar outra linha.
- **Conflicts**: mesmo ID com medidas diferentes; rejeitado com HTTP 409, preservando o original.
- **Device queue / dropped**: valores relatados pelo dispositivo no último contato, não uma leitura remota garantida do estado atual.

Os contadores do receptor são acumulados no banco e permanecem ao reiniciar. Os contadores de entregas/tentativas do cliente sintético são da sessão; a fila pendente e seu total de descartes persistem em disco. A rejeição por dados inválidos não conta como nova amostra. Falhas de token não estabelecem contato válido.

**Export connection report** salva um JSON de diagnóstico sem senha/token. **History & events → Export CSV** exporta todas as medições da origem selecionada, incluindo a informação de transporte e calibração.

## Conectar ESP32 físico depois

1. Confira sensores, ligações e calibração no manual principal e em **Sensors & calibration**.
2. PC e placa na mesma rede privada; para ESP32 clássico, rede Wi-Fi de 2,4 GHz.
3. Em IoT settings, use host `0.0.0.0`, porta `8765` e Start receiver.
4. Copie o token pelo botão apropriado. No Windows, obtenha o IPv4 do PC com `ipconfig`.
5. No firmware, copie `secrets.example.h` para `secrets.h` e preencha Wi-Fi, token e `http://IP_DO_PC:8765/api/readings`.
6. Arduino IDE: configure a placa ESP32 e instale DHT sensor library, Adafruit Unified Sensor, BH1750 de claws e **ArduinoJson versão 7**.
7. Grave `firmware/greenhouse_esp32/greenhouse_esp32.ino`. O firmware precisa ser o da V3 para os novos heartbeats e diagnósticos.
8. Abra o monitor serial em 115200 baud e selecione **LIVE ESP32** no painel.
9. A placa amostra a cada 60 segundos, envia sinais de presença a cada cerca de 30 segundos e tenta reenviar amostras pendentes com espera progressiva após falhas.
10. O solo real continua indisponível até que as referências medidas sejam confirmadas em Sensors & calibration.

`0.0.0.0` é endereço para escutar no PC, não o IP a colocar no ESP32. Permita a conexão na rede privada quando o firewall pedir. Não exponha esse HTTP local pela internet. O protocolo inclui token, mas não TLS. O exemplo não grava nem opera relé, bomba ou válvula.

O firmware V3 verifica o corpo JSON da confirmação antes de retirar a amostra da fila. ID e origem precisam coincidir. Dados inválidos/conflitantes são descartados e contabilizados; falhas transitórias ou de autenticação mantêm a amostra para nova tentativa. Se faltar sensor, a placa não inventa medições; relata falha pelo heartbeat quando houver conexão.

## Validação física pendente

A comunicação HTTP foi testada por software, sem uma placa física. A instalação, a compilação do sketch, a resposta dos sensores e a execução visual no Windows devem ser verificadas localmente. A V3 entrega o código e o roteiro; não declara essa etapa física concluída.

Use `docs/HARDWARE_VALIDATION.csv` para registrar cada verificação. O formulário começa como PENDING e não é preenchido automaticamente pelos testes sintéticos.

## Testar sem janela gráfica

Para usar somente o receptor: `python receiver_main.py` (loopback) ou `python receiver_main.py --lan` (rede privada).

Em outro terminal: `python test_device.py --duration 60 --offline-first 10`.

Não execute esse receptor e o receptor da GUI simultaneamente na mesma porta. Para a maioria dos usos, basta executar main.py e usar os botões da aba Connectivity lab.

Todos os testes: `python run_v3_checks.py`. O relatório será salvo em `exports/v3_software_validation.json`. Testes usam bancos temporários e não preenchem o seu histórico físico.

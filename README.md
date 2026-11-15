# jornada

Rastreio pessoal do tempo de trabalho no desktop Linux (GNOME/Wayland) e banco de horas.
Substituiu o ActivityWatch (`aw-server` + `awatcher` + `aw-watcher-mic`), o rastreador
`work-tracking` e a planilha `resumo 2025-10-20.xlsx`.

## Objetivo

1. **Medir o tempo trabalhado** com mais detalhe do que hoje: atividade de teclado/mouse,
   microfone em uso (reuniões), janela/aplicativo em foco e, opcionalmente, uma gravação de
   tela em baixa resolução para revisar o dia.
2. **Preencher o banco de horas** no próprio aplicativo, substituindo a planilha.

## O banco de horas de hoje (planilha)

Uma linha por dia:

| Coluna | Significado |
| --- | --- |
| Data | o dia |
| Realizado | horas trabalhadas (antes vindas do ActivityWatch) |
| Distribuído | horas previstas no dia (8h normal; 4h, 7h ou 9h30 em períodos de jornada diferente; vazio em fim de semana) |
| Delta (Horas) | saldo acumulado: `Σ Distribuído − Σ Realizado` (negativo = horas a favor) |
| Delta (Dias) | saldo em dias de 8h |
| Observação | ajustes manuais: "Script não rodou", feriado, day off, curso, viagem, WakaTime, uso pessoal |

O que o app precisa cobrir: jornada prevista configurável por período, feriados e day offs,
lançamentos manuais (correção quando o rastreio falhou, desconto de uso pessoal), saldo
acumulado em horas e dias, e exportação para planilha.

## Histórico importado

O histórico anterior ao jornada já está no banco, com a origem marcada em cada span: `aw`
(ActivityWatch, de 2026-03-02 a 2026-11-03) e `work-tracking` (o rastreador antigo, de
2025-06-30 a 2026-02-27); os spans medidos pelo próprio jornada têm origem `jornada`. As duas
fontes foram desinstaladas, e o comando `jornada import` que as lia saiu junto.

## Instalar como serviço

Requisitos do sistema (Ubuntu/GNOME): `python3-gi`, `gir1.2-ayatanaappindicator3-0.1`,
`gir1.2-gtk-3.0` e a extensão `ubuntu-appindicators@ubuntu.com` ligada.

```bash
bash scripts/deploy.sh              # instala ou atualiza (idempotente)
systemctl --user is-active jornada  # active
journalctl --user -u jornada -n 50  # logs
jornada status                      # versão, caminhos e user_version do banco
bash scripts/deploy.sh --uninstall  # remove unidade e venv; os dados ficam
```

O serviço sobe com a sessão gráfica, mostra o ícone na barra superior (rótulo, "Pausar
rastreio", "Depuração e regras", "Sair") e o systemd o religa se cair. A configuração opcional fica em
`~/.config/jornada/config.toml` (`db_path`, `start_paused`); os dados, em
`~/.local/share/jornada/`.

## Regras de detecção e eventos (depuração)

O que conta como tempo ativo é decidido por regras desta máquina, guardadas no banco e aplicadas
pelo serviço no tick seguinte (5 s), sem reiniciar. Elas valem dali em diante: nunca reescrevem
dias já registrados.

| Regra | Padrão | O que faz |
| --- | --- | --- |
| `input.minStreakSeconds` | 10 | teclado/mouse só conta depois de uso **contínuo** por esse tempo; a contagem começa no início da sequência. Menos que isso é um esbarrão e só vira evento. `0` conta na hora |
| `input.streakGapSeconds` | 10 | maior pausa entre entradas que ainda mantém a sequência contínua |
| `input.idleSeconds` | 180 | sem teclado/mouse por esse tempo, e sem microfone ou câmera, a contagem para (cortada na última entrada) |
| `input.ignoreApps` | — | `wm_class` de apps cujo foco não conta como teclado/mouse (ex.: `spotify`) |
| `mic.enabled`, `mic.minSeconds` | sim, 0 | microfone em uso conta mesmo sem teclado/mouse, depois desse tempo ligado |
| `camera.enabled`, `camera.minSeconds` | não, 0 | câmera em uso (um processo com `/dev/video*` aberto, ou o PipeWire servindo a câmera) conta como o microfone |
| `events.verbose` | não | grava também cada leitura dos detectores (muitos eventos; para depurar por pouco tempo) |
| `events.retentionDays` | 7 | eventos mais antigos são apagados a cada hora |

Cada decisão dos detectores vira um **evento**: atividade confirmada, esbarrão ignorado,
ociosidade, microfone/câmera em uso ou ignorados por serem curtos, tela bloqueada, app em foco,
pausa, regra alterada e falha de coletor.

- **Página:** "Depuração e regras" no menu da bandeja abre `http://127.0.0.1:8765/debug.html`
  com o estado ao vivo de cada detector, o formulário das regras e o log de eventos filtrável.
  Como os eventos carregam títulos de janela, a página só responde com o token da bandeja.
- **Terminal:**

  ```bash
  jornada events -n 100 [--source input] [--kind filter]   # últimos eventos
  jornada settings                                         # regras em vigor (e o padrão de cada uma)
  jornada settings --set input.idleSeconds=120 --set camera.enabled=true
  jornada settings --set input.ignoreApps=spotify,steam
  jornada settings --reset                                 # volta tudo ao padrão
  ```

## Banco de horas

O saldo é o Realizado menos o Previsto, somado dia a dia desde o primeiro dia lançado (positivo =
horas a favor). O Realizado é o tempo ativo medido, corrigível por dia; o Previsto vem da jornada
por período (padrão 8h de segunda a sexta), com feriado/dayoff zerando o dia.

```bash
jornada sheet import "resumo.xlsx"            # histórico da planilha (idempotente)
jornada sheet export saida.xlsx [--de AAAA-MM-DD --ate AAAA-MM-DD]   # mesmo layout da planilha
jornada ledger                                # saldo e últimos dias no terminal
```

Com o serviço no ar, a bandeja mostra "Saldo: +12h30 (1,6 dia)" e "Abrir banco de horas" abre a
tela local em `http://127.0.0.1:8765/` (porta em `[web] port` do `config.toml`). Só leitura e
escrita vindas dessa página, que recebe um token por cookie; escritas sem ele levam 403.

## Capturas de tela

A captura vem **desligada por padrão** (opt-in). Ligada, com o serviço no ar e a tela
desbloqueada, o jornada grava a cada 60 s uma imagem reduzida da
tela (WebP, 640 px de largura, em geral menos de 60 KB) em
`~/.local/share/jornada/capturas/AAAA-MM-DD/HHMMSS.webp`. O detalhe de cada dia no banco de
horas mostra a faixa de miniaturas e abre a imagem ampliada ao clicar.

- **Privacidade:** as imagens podem conter telas de reunião e dados da empresa e de terceiros.
  Ficam só nesta máquina (pasta `0700`, arquivos `0600`), nunca entram no git (`capturas/` está no
  `.gitignore`) e a página que as serve só responde com o token da bandeja.
- **Retenção:** dias com mais de 30 dias são apagados na subida do serviço e a cada hora
  (`retentionDays`), também com a captura desligada.
- **Pausas:** tela bloqueada, "Pausar rastreio" e "Pausar capturas" (menu da bandeja) não
  capturam. O microfone não pausa.
- **Como ligar e desligar:** em `~/.config/jornada/config.toml`, `[capture]` com
  `enabled = true` liga; sem a seção ou com `enabled = false` fica desligada (também há
  `intervalSeconds`, `width`, `retentionDays` para ajustar). Depois, `systemctl --user restart
  jornada`. Para apagar tudo, remova `~/.local/share/jornada/capturas/`.
- **Aviso do GNOME:** cada captura pelo portal faz o GNOME piscar a tela e tocar o som de
  captura; é o aviso do próprio sistema e não dá para silenciá-lo por aqui.
- **Mecanismo:** `org.freedesktop.portal.Screenshot` sem diálogo, válido para o serviço
  systemd de usuário; de um terminal o GNOME exige confirmação e recusa. Se o portal recusar, o
  menu mostra "Capturas: sem permissão" e o serviço só tenta de novo após 1 h.

## Contribuir e licença

Contribuições são bem-vindas: veja [CONTRIBUTING.md](CONTRIBUTING.md) (commits com `Signed-off-by`,
conforme o [DCO](DCO)) e o [código de conduta](CODE_OF_CONDUCT.md). Dúvidas vão para as
[issues](https://github.com/holetz/jornada/issues); vulnerabilidades, nunca em issue pública, seguem
o [SECURITY.md](SECURITY.md).

Distribuído sob a licença [MIT](LICENSE).

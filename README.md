# Tennis Match Condenser (Python)

App desktop per montaggio rapido di match di tennis amatoriali.

## Funzioni

- Caricamento video locale.
- Salti rapidi avanti/indietro: 5s, 10s, 30s (pulsanti + hotkeys).
- Marking `inizio punto` e `fine punto` con shortcut.
- Lista punti selezionati (taglio automatico tempi morti in export).
- Overlay punteggio stile TV durante il montaggio.
- Hotkeys configurabili da UI.
- Posizionamento overlay nei 4 angoli e scala configurabile.
- Undo azioni (bottone + hotkey).
- Caricamento multiplo di video MP4 consecutivi senza copie locali (concat solo in export).
- Area video ridimensionabile (splitter verticale).
- Barra di riproduzione con seek e tempo corrente/totale.
- Salvataggio/Caricamento progetto `.json` (segmenti, timestamp, score, overlay, sorgenti).
- Autosave automatico su `autosave_tennis_project.json` con richiesta di ripristino all'avvio.
- Preview scoreboard basata sulla timeline (stato preso dai segmenti già salvati).
- Preview testuale leggera del punteggio (Game/Pts) aggiornata in timeline.
- Supporto tie-break a 7 e super tie-break a 10 al posto del terzo set.
- Pulsanti `Punto ...` dinamici in base ai nomi giocatori.
- Servizio automatico: alternanza per game e regole tie-break (1 punto iniziale, poi ogni 2), con persistenza nel progetto.
- Modale progress export con percentuale, tempo trascorso e stima rimanente.
- Indicatore nel layout della durata stimata del video esportato.
- Colonna destra scrollabile.
- Pulsante `Preview grafica overlay` per esportare un frame di test con overlay reale (scala/posizione correnti).
- Intro automatica opzionale: frame da video + card TV (torneo, round, player/ranking) con durata configurabile.
- Outro automatica opzionale: frame da video (o stesso dell’intro) + card finale con score conclusivo.
- Export finale MP4 con soli punti giocati, con overlay opzionale.

## Requisiti

- Python 3.11+ consigliato.
- FFmpeg viene fornito da `imageio-ffmpeg`.

## Installazione

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Avvio

```bash
python app.py
```

## Build macOS 1.1 installabile

```bash
./build_macos.sh
```

Output:
- `dist/Tennis Match Condenser.app`
- `dist/Tennis-Match-Condenser-1.1.0-macOS.dmg`

## Hotkeys

- `Space`: Play/Pausa
- `Freccia sinistra/destra`: -/+5s
- `Shift + Freccia sinistra/destra`: -/+10s
- `Alt + Freccia sinistra/destra`: -/+30s
- `O` : Inizio punto
- `P` : Fine punto
- `Q` / `W`: Punto a Giocatore A/B
- `Ctrl+Z`: Undo
- `Esc`: Rilascia focus dai campi testuali

Nota: assegnando un punto (bottone o hotkey) viene chiusa automaticamente la clip corrente, se era aperta.

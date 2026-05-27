# Rain Vision — Custom Component per Home Assistant

Integrazione non ufficiale per il sistema di irrigazione smart **Rain Vision** di [RAIN S.p.A.](https://www.rain.it) in Home Assistant.

---

## Funzionalità

### Sensori
| Entità | Descrizione |
|---|---|
| `sensor.<device>_batteria` | Livello batteria del dispositivo (%) |
| `sensor.<nuvola>_batteria` | Livello batteria dell'hub Nuvola (%) |
| `sensor.<device>_programmi_attivi` | Programmi attualmente abilitati (A/B/C/D) |
| `sensor.<device>_pausa_meteo` | Stato pausa meteo per ogni programma |

### Switch
| Entità | Descrizione |
|---|---|
| `switch.<device>_<zona>` | Avvia/ferma irrigazione manuale su una zona |
| `switch.<device>_programma_<X>` | Abilita/disabilita un programma di irrigazione |

---

## Installazione

### Tramite HACS (consigliato)
1. Apri HACS → Integrazioni → Menu (⋮) → Repository personalizzati
2. Aggiungi l'URL del repository e seleziona categoria **Integrazione**
3. Cerca "Rain Vision" e installala
4. Riavvia Home Assistant

### Manuale
1. Copia la cartella `custom_components/rainvision` nella tua cartella `config/custom_components/`
2. Riavvia Home Assistant

---

## Configurazione

1. Vai su **Impostazioni → Dispositivi e servizi → Aggiungi integrazione**
2. Cerca **Rain Vision**
3. Inserisci email e password del tuo account rainvision.it
4. Conferma — le entità verranno create automaticamente

---

## Struttura entità

Per ogni impianto configurato vengono create:

- **1 dispositivo Nuvola** (hub Wi-Fi) con sensore batteria
- **1 dispositivo Pure Vision** per ogni centralina, con:
  - Sensore batteria
  - Sensore programmi attivi
  - Sensore pausa meteo
  - Switch per ogni zona (es. Prato 1, Prato 2, Piante, Orto)
  - Switch per ogni programma (A/B/C/D)

---

## ⚠️ Note importanti

### Endpoint comandi da verificare
Gli endpoint `ManualStart`, `ManualStop` e `SetProgramActive` sono stati dedotti dalla struttura dell'API. **Prima di usare gli switch**, verifica con DevTools quali URL vengono chiamati quando:
- Avvii un'irrigazione manuale
- Fermi un'irrigazione
- Abiliti/disabiliti un programma

Poi aggiorna `api.py` con gli URL corretti.

### Token di autenticazione
Il token viene salvato nella config entry e riutilizzato. Se scade, il componente tenta automaticamente un nuovo login con email e password.

### Polling
I dati vengono aggiornati ogni **60 secondi** (modificabile in `const.py` → `UPDATE_INTERVAL`).

---

## Sviluppo e contributi

Il file `manual` nel JSON del dispositivo è una stringa hex che codifica lo stato delle zone. Se trovi la decodifica corretta, apri una PR!

---

## Disclaimer

Questa è un'integrazione **non ufficiale**, non affiliata con RAIN S.p.A. Usala a tuo rischio.

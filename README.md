# Rainvision — Integrazione Home Assistant

Integrazione custom per Home Assistant che si connette alle API cloud di **Rainvision v5** per monitorare il tuo impianto di irrigazione smart.

## Entità create

### Sensori (`sensor`)
| Entità | Descrizione |
|---|---|
| `sensor.rainvision_batteria_irrigatore` | Batteria del dispositivo PURE VISION-EV (%) |
| `sensor.rainvision_batteria_nuvola` | Batteria della Nuvola (%) |
| `sensor.rainvision_programmi_attivi` | Programmi attualmente attivi (es. `A B C D`) |
| `sensor.rainvision_versione_firmware` | ID firmware installato |
| `sensor.rainvision_temperatura_meteo` | Temperatura meteo dal servizio previsioni (°C) |
| `sensor.rainvision_probabilita_pioggia` | Probabilità di pioggia (%) |
| `sensor.rainvision_vento` | Velocità vento (m/s) |
| `sensor.rainvision_variabile_irrigazione` | Variabile di aggiustamento irrigazione basata sul meteo (%) |
| `sensor.rainvision_prato_1` | Zona "Prato 1" |
| `sensor.rainvision_prato_2` | Zona "Prato 2" |
| `sensor.rainvision_piante` | Zona "Piante" |
| `sensor.rainvision_orto` | Zona "Orto" |

### Binary sensor (`binary_sensor`)
| Entità | Descrizione |
|---|---|
| `binary_sensor.rainvision_connesso_al_cloud` | Connettività cloud |
| `binary_sensor.rainvision_programma_a_meteo_ok` | Il meteo consente l'esecuzione del programma A |
| `binary_sensor.rainvision_programma_b_meteo_ok` | Il meteo consente l'esecuzione del programma B |

### Switch (`switch`)
| Entità | Descrizione |
|---|---|
| `switch.rainvision_programma_a` | Stato programma A (sola lettura) |
| `switch.rainvision_programma_b` | Stato programma B (sola lettura) |
| `switch.rainvision_programma_c` | Stato programma C (sola lettura) |
| `switch.rainvision_programma_d` | Stato programma D (sola lettura) |

> **Nota:** gli switch riflettono lo stato attivo dei programmi ma non possono attivare/disattivare i programmi via cloud (l'API Rainvision non espone questo endpoint). Usa i switch come condizioni nelle automazioni HA.

---

## Installazione

### Metodo 1 — HACS (consigliato)
1. In HACS → **Integrations** → menu ⋮ → **Custom repositories**
2. Aggiungi l'URL del repository, categoria `Integration`
3. Cerca "Rainvision" e installa
4. Riavvia Home Assistant

### Metodo 2 — Manuale
1. Copia la cartella `custom_components/rainvision/` in `<config>/custom_components/`
2. Riavvia Home Assistant

---

## Configurazione

1. **Impostazioni → Dispositivi e servizi → Aggiungi integrazione**
2. Cerca **Rainvision**
3. Inserisci:
   - **Email** e **Password** del tuo account rainvision.it
   - **PUID Nuvola**: il PUID del tuo hub NUVOLA VISION (inizia con `2000...`)
   - **PUID Irrigatore**: il PUID del tuo irrigatore PURE VISION (inizia con `1000...`)

> I PUID si trovano nell'app Rainvision → dettaglio dispositivo, oppure nel file HAR di questa configurazione.

---

## Dove trovare i PUID

- **PUID Nuvola**: `nuvola/stat` → campo `cloud.puid`
- **PUID Irrigatore**: `nuvola/device` → campo `device.puid`

Esempio dai tuoi dati:
- Cloud PUID: `2000001121`
- Device PUID: `1000005059`

---

## Automazione esempio

```yaml
# Sospendi le notifiche se sta per piovere
automation:
  - alias: "Rainvision - avviso irrigazione annullata"
    trigger:
      - platform: state
        entity_id: binary_sensor.rainvision_programma_a_meteo_ok
        to: "off"
    action:
      - service: notify.mobile_app
        data:
          title: "Rainvision"
          message: "Il programma A è stato sospeso per pioggia prevista"
```

```yaml
# Aggiorna dashboard con batteria bassa
automation:
  - alias: "Rainvision - batteria bassa irrigatore"
    trigger:
      - platform: numeric_state
        entity_id: sensor.rainvision_batteria_irrigatore
        below: 20
    action:
      - service: persistent_notification.create
        data:
          title: "Rainvision"
          message: "Batteria irrigatore al {{ states('sensor.rainvision_batteria_irrigatore') }}%"
```

---

## Intervallo aggiornamento

Di default ogni **60 secondi**. Modifica `SCAN_INTERVAL_SECONDS` in `const.py` se necessario.

# Manual test scripts

Scripts for checking real hardware and services by hand. They are **not** run
by `pytest` (they need a live Asterisk server, MQTT broker or phone).

| Script | Checks |
|---|---|
| `call*_succes.py` | AMI `Originate`: rings the SIP extensions |
| `sms*_succes.py` | AMI `MessageSend`: SIP text message |
| `combine*_succes.py`, `draft.py` | call + message together (early experiments) |
| `mqtt_test.py` | connects to the broker from `.env` and prints valid fall messages |

The AMI scripts still hold the local lab credentials (`hx` / `123`) from the
thesis setup. Never point them at a production Asterisk.

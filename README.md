# FelicaRelay
Relay felica exchange.

# Requirements
Two RC-S380.

# How to use
Connect RC-S380 to your computer, then Replace driver to WinUSB with Zadig (Windows).

Place a card to either Reader. Execute via

`python relay.py`

makes another reader a emulator.

# Replace
It can replace exchange.

For example, replace UNENCRYPTED decimal data `1000` to `12345`

`python relay.py -d 1000 12345`

It is as same as

`python relay.py -r e803 3930`

in hex mode.
# FelicaRelay
Relay felica exchange.

# Requirements
Two RC-S380.

# How to use
Connect RC-S380 to your computer, then Replace driver to WinUSB with Zadig (Windows).

`python relay.py`

# Replace
It can replace exchange.

For example, replace UNENCRYPTED decimal data `1000` to `12345`

`python -d 1000 12345`

It is as same as

`python -r e803 3930`

in hex mode.
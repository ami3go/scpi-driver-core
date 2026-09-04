# v26.09 — N6775A measurement capability correction

- **Python package:** 26.9.0
- **Archive:** `rf_keysight_n6700_v26.09.zip`
- **Internal root:** `rf_keysight_n6700/`

## Problem

The real USB run completed 17 of 19 enabled tests, but measurement testing sent `MEAS:POW?` to N6775A channels. The N6700 programmer reference limits direct power measurement to N676xA and N678xA SMU modules. N6775A returned `+310,"The command is not supported by this model"`; the unanswered query also produced `-420,"Query UNTERMINATED"`.

The same run exposed two Robot harness type defects: the channel remained a command-line string when compared with integer channel lists, and a local `${channel}` measurement variable overwrote `${CHANNEL}` because Robot variable names are case-insensitive.

## Changes

- N6775A and other basic power modules now calculate power from voltage and current measurements.
- Direct `MEAS:POW?` is used only when module capability explicitly supports simultaneous power measurement.
- The measurement aggregate reuses voltage/current samples instead of issuing unnecessary duplicate queries.
- Quoted-empty module option responses are normalized to an empty list.
- The self-check normalizes `${CHANNEL}` to an integer and uses `${channel_measurement}` for measurement dictionaries.
- Added exact trace assertions proving N6775A power measurement does not send `MEAS:POW?`.

## Compatibility

No public Robot keyword was removed or renamed. `Measure N6700 Power` retains the same Robot-compatible dictionary schema; only `power_source` changes from an invalid attempted instrument query to `calculated` on N6775A.

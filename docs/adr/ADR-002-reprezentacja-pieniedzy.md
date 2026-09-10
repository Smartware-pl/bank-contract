# ADR-002: Pieniądze to long w groszach + waluta

- Status: Przyjęty
- Data: 2026-09-07

## Kontekst
Liczby zmiennoprzecinkowe są niedopuszczalne dla pieniędzy; `BigDecimal` wszędzie jest rozwlekły, wolny i zaprasza do niespójnej skali/zaokrągleń; dedykowana biblioteka money to zależność za mały zysk w jednowalutowym sandboxie.

## Decyzja
Value object `Money(long minor, Currency currency)` w `common`. DB `NUMERIC(19,0)` + `CHAR(3)`. JSON `{"minor","currency"}`. `BigDecimal` tylko wewnątrz kalkulatora odsetek, zaokrąglany `HALF_EVEN` raz na granicy. `double`/`float` dla kwot zabronione w całym repo (reguła lintera + code review).

## Konsekwencje
+ Dokładna arytmetyka, trywialna równość, szybkie sumy w SQL.
+ Frontend nigdy nie liczy; tylko formatuje.
− Wielowalutowość będzie wymagać modułu konwersji; kolumna waluty jest od pierwszego dnia, więc migracje będą addytywne.
− Stopy i procenty to punkty bazowe (`int`), nie ułamki dziesiętne — udokumentowane w słowniku.

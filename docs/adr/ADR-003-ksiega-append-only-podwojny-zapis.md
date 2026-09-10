# ADR-003: Append-only księga podwójnego zapisu jest źródłem prawdy

- Status: Przyjęty
- Data: 2026-09-07

## Kontekst
Kolumna `balance` aktualizowana w miejscu jest prosta, ale nieaudytowalna i rozjeżdża się przy bugach lub współbieżności. Event sourcing całych agregatów jest cięższy niż potrzeba. Podwójny zapis to własny, sprawdzony model spójności tej domeny.

## Decyzja
Wszystkie ruchy pieniędzy to wiersze `journal_entry` z ≥2 zerosumowymi wierszami `posting`. Tabele są append-only (trigger DB). Salda są wyliczane; `balance_snapshot` to uzgadniany cache. Korekty to zapisy storna. Do tych tabel pisze tylko moduł `ledger`; pozostałe używają `LedgerApi`.

## Konsekwencje
+ Każde saldo jest wytłumaczalne; niezmiennik GL to jednolinijkowy test property.
+ Uzgodnienie na EOD wykrywa każdy bug, który błędnie przesunął pieniądze.
− Odczyt salda to SUM; snapshoty + indeksy na `(gl_account_code, business_date)` utrzymują go tanim.
− Developerzy muszą myśleć w Wn/Ma; słownik i plan kont w `domain-model.md` są lekturą obowiązkową.

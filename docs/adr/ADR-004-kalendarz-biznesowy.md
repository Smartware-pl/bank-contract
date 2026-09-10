# ADR-004: Data biznesowa to dane, nie zegar systemowy

- Status: Przyjęty
- Data: 2026-09-07

## Kontekst
Odsetki, kapitalizacja i zlecenia stałe zależą od tego, „jaki jest dzień" dla banku. Użycie czasu zegarowego czyni testy wolnymi lub niestabilnymi i uniemożliwia pokazanie miesięcy naliczeń w kilka minut.

## Decyzja
`batch.business_day` trzyma dokładnie jeden dzień `OPEN`. Cała logika biznesowa pyta `BusinessCalendarApi.currentBusinessDate()`. Dzień przesuwa się wyłącznie przez EOD. Zegarowy `Clock` jest wstrzykiwany i używany tylko do znaczników audytu oraz do harmonogramu wyzwalacza EOD. Dev/test mogą przewijać czas, uruchamiając EOD wielokrotnie.

## Konsekwencje
+ Deterministyczne testy; „3 miesiące odsetek" to 3-sekundowy test scenariuszowy.
+ Jasna semantyka odcięcia dla księgowań (problem `business-day-closed` podczas `CLOSING`).
− Dwa pojęcia „dzisiaj" — `CLAUDE.md` §5 zabrania `LocalDate.now()` w kodzie biznesowym, żeby ich nie mieszać.

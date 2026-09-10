# ADR-001: core-api jest modularnym monolitem

- Status: Przyjęty
- Data: 2026-09-07

## Kontekst
Jeden developer, domena (księga podwójnego zapisu, płatności, odsetki), w której transakcje obejmujące kilka modułów są normą, i chęć zachowania opcji podziału w przyszłości. Mikroserwisy pomnożyłyby pracę przy wdrożeniu, obserwowalności i spójności bez zysku w tej skali.

## Decyzja
`core-api` to jeden wdrażalny artefakt Spring Boot zorganizowany w application modules Spring Modulith. Każdy moduł ma własny schemat Postgresa; moduły komunikują się wyłącznie przez pakiety `api` i eventy domenowe; `ApplicationModules.verify()` pilnuje granic w CI. Ten sam jar działa w profilach `api` i `batch`.

## Konsekwencje
+ Jedna transakcja obejmuje payments + ledger + accounts — poprawność jest łatwa.
+ Jedna rzecz do uruchomienia, testowania i debugowania.
− Dyscyplina modułów opiera się na teście verify i na `CLAUDE.md` §5; leniwy skrót jest legalny dla kompilatora, nielegalny dla CI.
− Skalowanie jest pionowe, dopóki moduł nie zostanie wyodrębniony (zasada schemat-per-moduł utrzymuje tę możliwość).

# ADR-005: Osobne repozytoria per aplikacja, wspólny kontrakt jako submoduł

- Status: Przyjęty
- Data: 2026-09-07

## Kontekst
Do projektu dołącza druga osoba; chcemy podzielić aplikacje między siebie i pracować niezależnie (własne CI, własny rytm merge'ów, własne uprawnienia). Monorepo dawało za darmo „zmiana kontraktu = zmiana docs w tym samym commicie", ale utrudnia niezależną pracę i własność.

## Decyzja
Sześć repozytoriów: `bank-contract` (konstytucja, docs, OpenAPI), cztery repo aplikacji, `bank-infra` (compose, Keycloak, e2e). Każde repo aplikacji ma `bank-contract` jako submoduł git w `contract/`, przypięty do commita; klienty i interfejsy generują się lokalnie z submodułu. Kontrakt zmienia się wyłącznie przez PR do `bank-contract` z review drugiej osoby; zmiany w `/api/v1` są addytywne. `bank-infra` uruchamia e2e na obrazach `main` wszystkich repo.

## Konsekwencje
+ Jasna własność i niezależne CI; Claude Code fizycznie nie widzi kodu innych aplikacji — czyta `contract/docs`.
+ Przypięty submoduł = jawna wersja kontraktu; niezgodność wychodzi w e2e, nie w produkcji.
− Zmiana kontraktu to dwa–trzy PR-y zamiast jednego commita; submoduły wymagają dyscypliny (`git submodule update --init` po klonie, świadome podbijanie).
− Refaktor przekrojowy jest droższy; zasada addytywności w `v1` to jedyne, co chroni przed rozjazdem wersji.
Zastępuje wpis o monorepo w `CLAUDE.md` §3 i `architecture.md` §1a.

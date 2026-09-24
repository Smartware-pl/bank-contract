# Architektura

Sandboxowy system bankowy budowany przez dwuosobowy zespół. Pięć wdrażalnych aplikacji, jedna baza, jeden broker zdarzeń, jeden dostawca tożsamości, siedem repozytoriów.
Ten dokument opisuje, *co istnieje i dlaczego*. Jak aplikacje ze sobą rozmawiają — w `integration-contracts.md`.

## 1. Aplikacje

| Aplikacja | Technologia | Rola | Ma własne dane? |
|---|---|---|---|
| `core-api` | Java 21 / Spring Boot / Modulith | Cała logika biznesowa i cała persystencja. Wystawia REST API dla UI, publikuje zdarzenia na szynę (przez outbox), konsumuje zdarzenia izby rozliczeniowej, uruchamia zadania batchowe. | Tak — jedyna aplikacja z połączeniem do Postgresa i jedyne źródło prawdy. |
| `customer-web` | Next.js | UI klienta: rachunki, historia, przelewy, zlecenia stałe. | Nie. Rozmawia tylko z core-api. |
| `backoffice-web` | Next.js | Konsola operatora: klienci, rachunki, ręczne księgowania, przeglądarka GL, sterowanie dniem roboczym. | Nie. Rozmawia tylko z core-api. |
| `clearing-sim` | Spring Boot (cienki) | Symuluje izbę rozliczeniową: konsumuje `payment.posted` (zewnętrzne), po opóźnieniu publikuje rozliczenie lub zwrot, publikuje przelewy przychodzące. Z bankiem rozmawia wyłącznie przez szynę; HTTP ma tylko dla admina/testów. | Własny, malutki stan w pamięci/pliku; nigdy nie dotyka bazy banku. |
| `notifications` | Spring Boot (cienki) | Konsumuje zdarzenia z szyny i wysyła e-maile (kody potwierdzeń, potwierdzenia przelewów, kapitalizacja). Wzorcowy zewnętrzny konsument. | Własny `inbox` (SQLite lub własny schemat w Postgresie — ADR-006) do deduplikacji. Nie dotyka danych banku. |

Infrastruktura pomocnicza (`bank-infra/docker-compose.yml`): PostgreSQL 16, Redpanda (Kafka API) + Redpanda Console, Keycloak 25, Mailpit.

Kierunek zależności:

```
customer-web ──┐  REST (sync)
backoffice-web ┼──────────────▶ core-api ──▶ PostgreSQL
                                  │  ▲             
                     outbox relay │  │ consumer (payments)
                                  ▼  │
                          ┌── Redpanda (szyna zdarzeń) ──┐
                          │              ▲               │
                          ▼              │               ▼
                    notifications   clearing-sim    (przyszli konsumenci)
                          │
                          ▼
                       Mailpit (SMTP)
Keycloak ◀── UI (OIDC), core-api (JWT)
```

Nikt nie wywołuje aplikacji webowych. `core-api` nie wywołuje nikogo przez HTTP. Wszystko asynchroniczne między aplikacjami idzie przez szynę (tematy i zdarzenia — kontrakty §4–5).

## 1a. Repozytoria

| Repo | Zawartość | Właściciel (CODEOWNERS) |
|---|---|---|
| `bank-contract` | `CLAUDE.md` (konstytucja), `docs/`, `openapi/` — jedyne wspólne repo; **wszystko, co przekracza granicę aplikacji, zmienia się tutaj** | oboje; każdy PR wymaga review drugiej osoby |
| `bank-core-api` | backend | osoba A |
| `bank-customer-web` | UI klienta | osoba B |
| `bank-backoffice-web` | UI operatora | osoba B |
| `bank-clearing-sim` | symulator izby | osoba B (lub A — mały) |
| `bank-notifications` | konsument zdarzeń → e-mail | osoba B |
| `bank-infra` | docker-compose całego stacku (Redpanda, Postgres, Keycloak, Mailpit, aplikacje), realm Keycloak, seedy, testy e2e Playwright | oboje |

Każde repo aplikacji ma `bank-contract` jako **submoduł git w `contract/`**, przypięty do konkretnego commita. Ten commit to „wersja kontraktu, którą implementuję". Klienty i interfejsy REST generują się lokalnie z `contract/openapi/*.yaml`, klasy zdarzeń z `contract/asyncapi/asyncapi.yaml` (`asyncapi-generator` / `jsonschema2pojo` z osadzonych schematów) — w czasie builda, bez rejestru paczek.

Konwencja katalogu roboczego: wszystkie repa sklonowane obok siebie w `~/bank/`; `bank-infra/docker-compose.yml` domyślnie używa obrazów z GHCR publikowanych przez CI każdego repo (`main`), a `docker-compose.override.yml` pozwala zbudować lokalnie tę aplikację, nad którą właśnie pracujesz.

### Przepływ zmiany kontraktu

1. PR do `bank-contract`: zmiana `openapi/*.yaml` lub `asyncapi/asyncapi.yaml` **i** `docs/integration-contracts.md` (i/lub `domain-model.md`) w tym samym PR. Review drugiej osoby. Merge.
2. PR do repo aplikacji: podbicie submodułu `contract` do nowego commita, regeneracja, implementacja, testy.
3. Druga strona kontraktu podbija submoduł, gdy jest gotowa — zmiany w `v1` są **wyłącznie addytywne** (nowe pola opcjonalne, nowe endpointy, nowe zdarzenia, nowe wartości enumów oznaczone w docs jako „nowe od <data>"); usunięcie lub zmiana znaczenia pola to `v2` REST lub `version+1` zdarzenia i ADR. Konsumenci zdarzeń ignorują nieznane pola i nieznane `type`.
4. E2E w `bank-infra` biegną na obrazach z `main` wszystkich repo — to jest miejsce, gdzie niezgodność wersji wychodzi na jaw.

## 2. core-api — modularny monolit

Jeden projekt Gradle, jedna JVM, jedna baza Postgres. Moduły to application modules Spring Modulith;
każdy ma własny schemat DB. Granice weryfikuje `ApplicationModules.verify()` w CI.

| Moduł | Odpowiedzialność | Zależy od (tylko api) |
|---|---|---|
| `common` | `Money`, `Iban`, identyfikatory, wiring `Clock`, problem-details, filtr idempotencji, correlation id | — |
| `customers` | Rekordy klientów, status, powiązanie z `sub` z Keycloak | common, outbox, batch (data biznesowa) |
| `accounts` | Produkty, rachunki, generowanie IBAN/NRB, saldo dostępne, blokady; implementuje też endpointy `/customers/*`, bo łączą klienta z rachunkami | common, ledger (odczyt sald), customers, outbox, batch (data biznesowa) |
| `ledger` | Plan kont, zapisy księgowe, postingi, storna, snapshoty sald | common, batch (data biznesowa i status dnia dla endpointów operatora) |
| `payments` | Przelewy wewnętrzne/zewnętrzne, potwierdzenia, zlecenia stałe, maszyna stanów płatności; konsument zdarzeń izby (`bank.clearing.*`) przez `inbox` | common, accounts, customers (e-mail do zdarzeń, klient z `sub`), ledger, batch (data biznesowa), outbox |
| `interest` | Harmonogramy stóp, dzienne naliczanie, kapitalizacja, podatek; od v0.4 implementuje `GET /me/products` (widok klienta harmonogramu); dane odsetkowe do `/me/accounts*` (które zostają w `accounts`) dostarcza zbiorczo przez zdarzenia Modulith (`AccountEvents.AccruedInterestQuery`, `ProductRatesQuery`) | common, accounts, customers, ledger, batch, outbox |
| `batch` | Kalendarz biznesowy, orkiestracja EOD, przebiegi zadań, blokady schedulera | common, outbox; publikuje `BusinessDayClosed`. Nie zależy od modułów księgowych — kroki EOD (snapshoty, naliczenia) wyzwala zdarzeniami Modulith, bo `ledger`, `payments` i `interest` zależą od `batch` (brak cykli) |
| `outbox` | Tabela outbox, relay publikujący na Redpandę (profil `batch`), rejestr `inbox` dla konsumowanych zdarzeń | common |
| `audit` | Przekrojowy dziennik audytu komend | common |

Zasady dla modułów są w root `CLAUDE.md` §5. Struktura wewnątrz modułu: `api/`, `domain/`, `application/`, `infrastructure/`.

### Profile uruchomieniowe

Ten sam jar działa w dwóch profilach:

- `api` — obsługuje HTTP, bez zadań cyklicznych.
- `batch` — bez publicznego HTTP poza `/actuator`; uruchamia zadania cykliczne (wyzwalacz EOD, relay outbox → Redpanda, zlecenia stałe) i konsumentów Kafka (`bank.clearing.*`). Używa ShedLock na DB, żeby kilka instancji batch nigdy nie uruchomiło tego samego zadania dwa razy.

Compose dev uruchamia jedną instancję z obydwoma profilami.

### Persystencja

- Jedna baza `bank`, schematy: `common`, `customers`, `accounts`, `ledger`, `payments`, `interest`, `batch`, `outbox`, `audit`, `shedlock`.
- Migracje Flyway per moduł w `src/main/resources/db/migration/<module>/` (repo `bank-core-api`).
- Kod jOOQ generowany z zmigrowanego schematu w czasie builda.
- Append-only na `ledger.journal_entry` i `ledger.posting` wymuszone triggerem `BEFORE UPDATE OR DELETE` rzucającym wyjątek.

### Zdarzenia

- W procesie: Spring Modulith `ApplicationModuleListener` z trwałym rejestrem publikacji (retry). Każdy moduł, którego zdarzenie ma wyjść na zewnątrz, dodatkowo zapisuje kopertę do `outbox.outbox` w tej samej transakcji.
- Poza proces: relay w profilu `batch` czyta `outbox.outbox` w kolejności, publikuje na Redpandę (klucz = `aggregateId`, temat wg katalogu §4), znaczy `published_at`. Producent idempotentny (`enable.idempotence=true`), `acks=all`.
- Do procesu: konsumenci Spring Kafka na `bank.clearing.*` zapisują `id` do `outbox.inbox` w tej samej transakcji, co skutek biznesowy; powtórka `id` → ack bez działania.
- Dlaczego relay z pollingiem, a nie Debezium/CDC: jeden kontener mniej, opóźnienie ~1 s jest akceptowalne, a zachowanie jest w pełni testowalne w Testcontainers. Można podmienić (ADR), interfejs outboxa się nie zmienia.

## 3. Aplikacje webowe

Obie aplikacje Next.js mają ten sam szkielet:

- Auth przez NextAuth (lub `oidc-client-ts`) do Keycloak; access token przekazywany do core-api jako `Authorization: Bearer`.
- Dostęp do API wyłącznie przez wygenerowany klient TypeScript z repo `bank-contract`. Regeneracja: `pnpm contract:gen`.
- Żadnej matematyki biznesowej w przeglądarce. Kwoty wyświetlane przez formatter przyjmujący `{minor, currency}`.
- `customer-web` może wołać tylko endpointy z tagiem `customer` w OpenAPI; `backoffice-web` używa tagów `operator`/`admin`.

## 4. clearing-sim

Cel: sprawić, żeby przelewy zewnętrzne wyglądały realnie bez drugiego banku — i pokazać cudzy system na szynie.

- Konsumuje `bank.payments.v1`, reaguje tylko na `payment.posted` z `external=true`; trzyma płatność przez konfigurowalny czas (domyślnie 5–30 s), potem publikuje `clearing.settled` albo `clearing.returned` na `bank.clearing.v1` (konfigurowalny odsetek zwrotów + lista „magicznych" IBAN-ów, które zawsze wracają).
- Publikuje `clearing.incoming_received` (przelew przychodzący) — z endpointu admina lub generatora ruchu (`POST /admin/traffic`), do zasilania rachunków testowych i e2e.
- Jedyne HTTP: `/admin/*` (bez auth w dev) i `/actuator`. Z `core-api` nie rozmawia po HTTP w ogóle.
- Celowo głupi: kolejka w pamięci + zrzut JSON przy zamknięciu. Utrata stanu nic nie psuje w banku — płatności zostają `POSTED`, dopóki nie przyjdzie rozliczenie albo operator nie zrobi ręcznego zwrotu.

## 4a. notifications

- Konsumuje `bank.customers.v1`, `bank.accounts.v1`, `bank.payments.v1`, `bank.interest.v1`; dla każdego znanego `type` ma szablon e-mail; nieznane `type` loguje i ignoruje.
- `inbox` do deduplikacji (SQLite w wolumenie kontenera — bez współdzielenia bazy banku).
- E-mail przez SMTP (Mailpit w dev). Kod potwierdzenia przelewu przychodzi w `payment.confirmation_requested` w polu `code` (jawny, tylko dla tego konsumenta; `core-api` trzyma wyłącznie hash) — to jedyny wyjątek od zasady „bez sekretów w payloadzie", odnotowany w kontraktach §4.
- Wzorcowy konsument: kolejne (np. `bank-statements`, `bank-analytics`) kopiują jego szkielet.

## 5. Przekrojowe

- **Tożsamość**: realm Keycloak `bank`; klienci `customer-web`, `backoffice-web`, `core-api` (`clearing-sim` nie ma klienta — nie woła core-api, patrz `integration-contracts.md` §2). Eksport realmu w `bank-infra/keycloak/realm-bank.json`.
- **Obserwowalność**: Actuator health/metrics; logi JSON z `correlationId`, `businessDate`, `module`; `correlationId` wędruje w kopercie zdarzenia, więc jeden przelew da się prześledzić przez wszystkie aplikacje. Redpanda Console pokazuje tematy i lag konsumentów. Prometheus/Grafana opcjonalne i poza zakresem do etapu 8.
- **Konfiguracja**: zmienne środowiskowe 12-factor, udokumentowane w `integration-contracts.md` §6. `bank-infra/.env.example` trzyma wartości dev.

## 6. Roadmapa i Definition of Done

Jeden etap na sesję Claude Code / PR. Etap jest gotowy, gdy jego DoD przechodzi na czystym `docker compose up`.

| # | Etap | Definition of done |
|---|---|---|
| 0 | Szkielet: repozytoria z submodułem `contract`, `bank-infra` compose (Postgres, Redpanda + Console, Keycloak, Mailpit), Flyway, test Modulith verify, CI w każdym repo, ADR-001..006 | `make up && make health` zielone w `bank-infra`; `ApplicationModules.verify()` przechodzi z pustymi modułami; tematy utworzone |
| 1 | `ledger`: plan kont, `LedgerApi.post`, constraint sumy zero, trigger append-only, storno, testy property | Da się zaksięgować i wystornować zapis endpointem operatora; GL bilansuje się do zera pod sekwencjami jqwik |
| 2 | `customers` + `accounts` + `outbox`: produkty, otwarcie rachunku, NRB, saldo z księgi, blokady; outbox + relay; `customer.created`, `account.opened` na szynie | Nowy klient dostaje NRB z saldem 0; zdarzenia widoczne w Redpanda Console z poprawną kopertą |
| 3 | `payments` wewnętrzne: idempotentne tworzenie, blokada → potwierdzenie → księgowanie; publikacja `payment.*` | Przelew A→B widoczny w obu historiach; powtórzone żądanie zwraca tę samą płatność; `payment.posted` na szynie |
| 4 | `bank-notifications`: konsument z inboxem, szablony, kod potwierdzenia e-mailem | Kod potwierdzenia dochodzi do Mailpit ≤ 2 s po utworzeniu przelewu; powtórzenie zdarzenia nie wysyła drugiego maila |
| 5 | `batch` + `interest`: kalendarz, EOD, naliczanie, kapitalizacja z podatkiem, zlecenia stałe; `businessday.closed`, `interest.capitalized` | Przewinięcie 3 miesięcy; salda zgodne z `docs/reference/interest-cases.csv`; mail o kapitalizacji |
| 6 | `customer-web`: logowanie, rachunki, historia, przelew, zlecenia stałe | Smoke Playwright przechodzi na stacku `bank-infra` |
| 7 | `bank-clearing-sim` + przelewy zewnętrzne w `core-api` (konsument `bank.clearing.v1` z inboxem, storno przy zwrocie, uznanie przy przychodzącym) | Przelew wychodzący kończy w `SETTLED` lub `RETURNED` bez żadnego HTTP między aplikacjami; przelew przychodzący uznaje rachunek; duplikat zdarzenia nie księguje dwa razy |
| 8 | `backoffice-web`: klienci, rachunki, ręczne księgowanie, przeglądarka GL, wyzwalacz EOD | Operator zamyka dzień z UI i widzi zapisy naliczeń |
| 9 | Wyciągi (PDF), opłaty, metryki, lag konsumentów w health; opcjonalnie SSE statusu płatności dla UI | System działa bez nadzoru przez symulowany miesiąc bez rozjazdów w uzgodnieniu i bez rosnącego lagu |
| 10 | Kontrakt v0.4 (F4 frontów): `GET /audit` nad istniejącym `audit.audit_log`, odsetki i `/me/products` dla klienta, `standingOrderId` w płatnościach i zlecenia stałe klienta dla operatora, `/me/notifications` (projekcja zdarzeń, ADR-008), `/me/beneficiaries`, `/ops/consumers` i `/ops/dlq` (AdminClient, ADR-007). Wyciągi, cennik i `POST /accounts/{id}/fees` z tego kontraktu realizuje etap 9 | Backoffice pokazuje wpis audytu po zwrocie płatności i lag grup konsumentów; klient widzi naliczone odsetki i powiadomienie o kapitalizacji po fast-forwardzie; żaden nowy endpoint nie zapisuje niczego do księgi poza `/accounts/{id}/fees` |

## 7. Świadome uproszczenia

Jedna waluta (PLN) w regułach, kolumna waluty wszędzie. Bez KYC/AML, kart, FX, multi-tenancy.
Jedna baza, jeden proces backendowy z logiką. Jeden broker, jedna partycja na temat w dev (klucz partycji ustawiony od początku, więc zwiększenie liczby partycji to konfiguracja). Bez schema registry — schematy w `asyncapi/`, walidowane testami kontraktowymi po obu stronach. Każde z tych założeń można zmienić przez ADR; granice modułów czynią to tanim.

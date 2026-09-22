# Bank — konstytucja projektu

Ten plik żyje w repo `bank-contract` i trafia do każdego repo aplikacji jako submoduł `contract/`. Claude Code wczytuje
go przez `CLAUDE.md` danego repo. Zawiera wyłącznie zasady, które się nie zmieniają, oraz wskazówki, gdzie szukać
szczegółów. Trzymaj go poniżej ~200 linii. Szczegóły należą do `docs/`, nie tutaj.

Ścieżki `docs/...` i `openapi/...` w tym pliku są względem repo `bank-contract`; w repo aplikacji znajdziesz je
pod `contract/docs/...` i `contract/openapi/...`.

Gdy ten plik i kod się różnią, wygrywa ten plik: popraw kod albo zaproponuj ADR zmieniający zasadę.
Nigdy nie odstępuj od zasad po cichu.

## 1. Czym jest ten projekt

Sandboxowy system bankowy budowany przez dwuosobowy zespół (ADR-005). Prawdziwa semantyka księgowa, nieprawdziwe pieniądze.
System ma *żyć*: dni robocze się zamykają, odsetki naliczają się i kapitalizują, przelewy przechodzą przez
symulowaną izbę rozliczeniową. Aplikacje komunikują się asynchronicznie przez szynę zdarzeń; HTTP służy tylko
do synchronicznych zapytań i komend z UI. Poprawność księgowa jest ważniejsza niż liczba funkcji. Błędne saldo to bug P0;
brakujący ekran w UI to pozycja w backlogu.

## 2. Przeczytaj, zanim cokolwiek ruszysz

| Kiedy | Czytaj |
|---|---|
| Zawsze | ten plik, potem `CLAUDE.md` w root repo aplikacji, nad którą pracujesz |
| Cokolwiek, co przekracza granicę aplikacji lub modułu | `docs/integration-contracts.md` — czytaj TO ZAMIAST kodu innych aplikacji |
| Produkujesz lub konsumujesz zdarzenie | `docs/integration-contracts.md` §4–5 i `asyncapi/asyncapi.yaml` |
| Dodajesz/zmieniasz encję, stan lub termin | `docs/domain-model.md` |
| Dotykasz pieniędzy, odsetek, EOD, limitów, IBAN | `docs/business-rules.md` |
| Decyzje strukturalne | `docs/architecture.md`, `docs/adr/` |

Kod innych aplikacji jest w innych repozytoriach i nie masz go — to celowe. Jeśli `docs/integration-contracts.md`
nie odpowiada na twoje pytanie — zatrzymaj się i powiedz o tym. Rozwiązaniem jest PR do `bank-contract`, nie zgadywanie
ani szukanie po dysku sąsiednich klonów.

## 3. Repozytoria

| Repo | Zawartość |
|---|---|
| `bank-contract` | ten plik, `docs/`, `openapi/openapi.yaml` (core-api REST), `asyncapi/asyncapi.yaml` (zdarzenia na szynie). Jedyne miejsce zmian przekraczających granicę aplikacji. |
| `bank-core-api` | Java 21 + Spring Boot 3, modularny monolit (Spring Modulith). Cała logika biznesowa. |
| `bank-customer-web` | Next.js (TS). UI bankowości dla klienta. |
| `bank-backoffice-web` | Next.js (TS). Konsola operatora/admina. |
| `bank-clearing-sim` | Mały serwis Spring Boot symulujący izbę rozliczeniową; rozmawia z bankiem wyłącznie przez szynę. |
| `bank-notifications` | Mały serwis Spring Boot: konsumuje zdarzenia z szyny, wysyła e-maile. Pierwszy „obcy" konsument. |
| `bank-infra` | docker-compose całego stacku (w tym broker), realm Keycloak, seedy, testy e2e Playwright. |

Każde repo aplikacji ma `bank-contract` jako submoduł w `contract/`, przypięty do commita. Klient/interfejsy HTTP
generują się z `contract/openapi/*.yaml`, klasy zdarzeń z `contract/asyncapi/asyncapi.yaml`, w czasie builda. Szczegóły i przepływ zmiany kontraktu: `docs/architecture.md` §1a.

## 4. Stack — ustalony, nie zamieniaj

- Backend: Java 21, Spring Boot 3.x, Spring Modulith, Spring Security (OAuth2 resource server), jOOQ, Flyway, PostgreSQL 16.
- Frontend: Next.js (App Router) + TypeScript, klient generowany z OpenAPI w `contract/openapi/`, Tailwind.
- Auth: Keycloak (realm `bank`). Aplikacje nigdy nie przechowują haseł.
- Szyna zdarzeń: Redpanda (Kafka API) — jeden broker w `bank-infra`, Redpanda Console do podglądu. Producenci: Spring Kafka. Serializacja JSON według koperty z kontraktów §4, schematy w `asyncapi/`. Bez schema registry (walidacja schematów w testach kontraktowych).
- Publikacja z `core-api` wyłącznie przez transactional outbox w Postgresie + relay. Bez Redisa, bez drugiego brokera.
- Mail: SMTP do Mailpit w dev.
- Testy: JUnit 5, jqwik (property-based), Testcontainers, REST Assured, Playwright.
- Build: Gradle (Kotlin DSL) dla Javy, pnpm workspaces dla TS. Root `Makefile` opakowuje typowe zadania.

Dodanie zależności wprowadzającej nową *kategorię* (cache, wyszukiwarka, ORM, drugi broker) wymaga najpierw ADR.

## 5. Zasady niepodważalne

### Pieniądze
- Kwota to `long` w jednostkach mniejszych (grosze) + kod waluty ISO 4217. Java: value object `Money(long minor, Currency ccy)` w `core-api/common`. DB: `NUMERIC(19,0)` + `CHAR(3)`. JSON: `{"minor": 12345, "currency": "PLN"}`.
- `double`/`float` dla pieniędzy jest zabronione wszędzie, łącznie z testami i frontendem.
- `BigDecimal` dozwolony tylko wewnątrz kalkulatora odsetek; zaokrąglany `HALF_EVEN` do groszy, zanim go opuści.
- Dziś reguły zakładają jedną walutę (PLN), ale każda kwota niesie walutę, a mieszanie walut w jednym zapisie to twardy błąd.

### Księga (moduł `ledger`)
- Każdy ruch pieniędzy to `journal_entry` z ≥2 wierszami `posting`, których kwoty sumują się dokładnie do zera.
- `journal_entry` i `posting` są append-only. Żadnego UPDATE ani DELETE — wymuszone triggerem w DB. Korekta to zapis odwrotny (storno) wskazujący na oryginał.
- Salda wynikają z postingów. `balance_snapshot` to cache zapisywany przez EOD i uzgadniany z postingami; nigdy nie jest źródłem prawdy.
- Każdy zapis ma `idempotency_key` (UNIQUE), `booking_date`, `value_date`, `business_date`.
- Do tabel księgi pisze tylko `ledger`. Inne moduły wołają `LedgerApi.post(...)`.

### Czas
- Chwile zapisuj jako `TIMESTAMPTZ` w UTC. Nigdy nie przechowuj lokalnego czasu zegarowego.
- Logika biznesowa używa `business_date` (`LocalDate`) pobranej z `BusinessCalendarApi`, nigdy `LocalDate.now()` ani `Instant.now()` bezpośrednio. Wstrzykuj `Clock`; testy nim sterują.

### Granice modułów (core-api)
- Moduły: `common`, `customers`, `accounts`, `ledger`, `payments`, `interest`, `batch`, `outbox`, `audit`. (`notifications` jest osobną aplikacją — patrz §3.)
- Każdy moduł ma własny schemat Postgresa o tej samej nazwie. Bez kluczy obcych między schematami, bez zapytań między schematami, bez współdzielonych tabel.
- Moduły rozmawiają wyłącznie przez pakiet `api` (interfejsy + DTO) albo przez publikowane eventy domenowe. `ApplicationModules.of(BankApplication.class).verify()` odpala się w CI i musi przechodzić.
- Eventy między modułami idą przez publikację eventów Spring Modulith; eventy wychodzące z procesu idą przez outbox (patrz dokument kontraktów).

### Szyna zdarzeń
- Między aplikacjami asynchronicznie idą **wyłącznie zdarzenia** — fakty w czasie przeszłym (`payment.posted`). Żadnych komend ani request-reply przez szynę. Jeśli coś ma się *stać* w innej aplikacji, publikujesz fakt, na który ona reaguje.
- Jedynym źródłem prawdy o stanie banku jest baza `core-api`. Zdarzenie jest pochodną zapisu w DB, nigdy odwrotnie: `core-api` publikuje wyłącznie przez outbox zapisany w tej samej transakcji, co zmiana stanu.
- Każda aplikacja konsumująca ma tabelę/rejestr `inbox` (id przetworzonych zdarzeń) i przetwarza idempotentnie. Duplikaty i zmiana kolejności między różnymi agregatami to normalność, nie błąd.
- Klucz partycji = `aggregateId`. Kolejność gwarantowana tylko w obrębie jednego agregatu.
- Koperta i katalog zdarzeń są w `docs/integration-contracts.md` §4 i `asyncapi/asyncapi.yaml`. Nowe zdarzenie lub nowe pole = PR do `bank-contract`. Pola tylko dodajesz; usunięcie lub zmiana znaczenia = nowa `version` zdarzenia, obie wersje publikowane równolegle przez okres przejściowy.
- Payload bez PII poza identyfikatorami i e-mailem tam, gdzie konsument musi wysłać wiadomość. Kwoty jako `{"minor","currency"}`.
- UI (Next.js) nie dotyka szyny — czyta stan przez REST.

### Komendy i współbieżność
- Każdy mutujący endpoint HTTP wymaga nagłówka `Idempotency-Key`. Powtórzenie zwraca oryginalny wynik.
- Księgowanie na rachunku bierze blokadę wiersza (`SELECT ... FOR UPDATE`) na rachunek/rachunki w deterministycznej kolejności (po id), żeby uniknąć deadlocków.
- Agregaty mają kolumnę `version`; równoległa modyfikacja zwraca HTTP 409.

### Bezpieczeństwo
- core-api jest OAuth2 resource server; role pochodzą z ról realmu w JWT: `CUSTOMER`, `OPERATOR`, `ADMIN`.
- Sprawdzanie własności (klient widzi tylko swoje rachunki) jest w warstwie serwisów, nie tylko w kontrolerach.
- Sekrety ze zmiennych środowiskowych. Nigdy nie commituj sekretów; domyślne wartości dev są w `bank-infra/.env.example`.
- Żadnego PII w logach. Loguj id, nie nazwiska ani IBAN-y (IBAN maskuj do ostatnich 4 znaków).

### API HTTP
- `bank-contract/openapi/openapi.yaml` to kontrakt. Kolejność: PR do `bank-contract` (YAML + docs) → merge → podbicie submodułu w repo aplikacji → regeneracja → implementacja. Nigdy nie pisz ręcznie kodu klienta w aplikacjach webowych i nigdy nie edytuj YAML-a wewnątrz `contract/` w repo aplikacji.
- Zmiany w `/api/v1` są wyłącznie addytywne (nowe opcjonalne pola, nowe endpointy, nowe wartości enumów). Usunięcie lub zmiana znaczenia to `/api/v2` i ADR.
- Wersjonowana ścieżka bazowa `/api/v1`. Błędy w formacie RFC 7807 `application/problem+json` ze stabilnym slugiem `type` (patrz dokument kontraktów).
- Paginacja kursorowa (`cursor`, `limit`), nigdy offsetowa.

## 6. Konwencje inżynierskie

- Układ pakietów w module: `<module>/api` (publiczny), `<module>/domain`, `<module>/application`, `<module>/infrastructure` (repozytoria jOOQ, kontrolery). Eksportowany jest tylko `api`.
- Nazewnictwo: DB `snake_case`, Java `camelCase`, JSON `camelCase`, enumy `UPPER_SNAKE`. Nazwy tabel w liczbie pojedynczej (`account`, `posting`).
- Migracje: `V<yyyyMMddHHmm>__<module>__<opis>.sql`, jeden moduł na plik, nigdy nie edytuj zaaplikowanej migracji.
- Logi: strukturalny JSON, zawsze z `correlationId`; każde przychodzące żądanie go dostaje.
- Commity: Conventional Commits, scope = aplikacja lub moduł (`feat(ledger): ...`). Jeden etap roadmapy na PR.
- Frontend: server components domyślnie, client components tylko dla interakcji; żadnych obliczeń biznesowych w przeglądarce (tylko prezentacja).

## 7. Testowanie — wymagane, nie opcjonalne

- `ledger`: testy property-based dowodzące, że dowolna sekwencja poprawnych komend utrzymuje bilans GL (suma wszystkich postingów = 0), a salda klientów równają się kontu kontrolnemu zobowiązań wobec klientów.
- `interest`: testy tabelaryczne, w tym rok przestępny, zmiana stopy w środku okresu, saldo ujemne, kapitalizacja z podatkiem.
- Każdy moduł: testy integracyjne na Postgresie z Testcontainers; żadnego H2, żadnych mocków bazy.
- Każdy endpoint HTTP z kontraktu ma co najmniej jeden test REST Assured na działającej aplikacji.
- EOD: test scenariuszowy, który seeduje rachunki, przewija N dni roboczych i porównuje salda z wyliczeniem referencyjnym.
- Frontend: smoke Playwright per ekran w `e2e/`.
- Testy potrzebujące „dzisiaj" ustawiają datę biznesową jawnie. Test wołający `LocalDate.now()` to bug.

## 8. Zasady współpracy z Claude Code

1. Zacznij od powtórzenia zadania własnymi słowami i wypisania, które sekcje docs go dotyczą. Jeśli w docs brakuje czegoś, czego potrzebujesz, powiedz to przed kodowaniem.
2. Rób najmniejszą zmianę, która spełnia Definition of Done etapu z `docs/architecture.md`. Bez spekulacyjnych abstrakcji, bez refaktorów „przy okazji".
3. Każda zmiana endpointu, zdarzenia, tematu, zmiennej środowiskowej, portu lub maszyny stanów zaczyna się od PR do `bank-contract` aktualizującego `openapi/` lub `asyncapi/` oraz `docs/integration-contracts.md` i/lub `docs/domain-model.md`. Pracując w repo aplikacji, nie implementuj niczego, czego nie ma w przypiętym `contract/` — zatrzymaj się i poproś o zmianę kontraktu.
4. Nowa decyzja strukturalna → nowy `docs/adr/ADR-NNN-*.md` (użyj szablonu). Nie decyduj po cichu.
5. Nigdy nie osłabiaj zasady z sekcji 5, żeby test przeszedł.
6. Przed ogłoszeniem „gotowe" uruchom weryfikację granic modułów, migracje na czystej bazie i dotknięte zestawy testów. Jeśli podbiłeś submoduł `contract`, napisz w opisie PR, z jakiego na jaki commit i co się zmieniło.
7. Gdy wahasz się między dwoma projektami, wybierz ten z mniejszą liczbą ruchomych części i odnotuj alternatywę w opisie PR.

## 9. Zabronione

`double`/`float` dla pieniędzy · `LocalDate.now()` w kodzie biznesowym · UPDATE/DELETE na tabelach księgi · SQL między schematami · ręcznie pisane klienty API · H2 · paginacja offsetowa · sekrety w git · komendy lub request-reply przez szynę · publikacja zdarzeń z pominięciem outboxa · bezpośrednie HTTP między `core-api` a `clearing-sim`/`notifications` · Redis/inna infrastruktura bez ADR · edycja plików w `contract/` z poziomu repo aplikacji · implementowanie endpointów, których nie ma w przypiętym kontrakcie · szukanie kodu innych aplikacji w sąsiednich katalogach.

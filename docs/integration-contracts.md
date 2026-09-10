# Kontrakty integracyjne

Wszystko, co jedna aplikacja musi wiedzieć, żeby rozmawiać z drugą — tak, żeby nikt nie musiał czytać kodu innej aplikacji.
**Każda zmiana endpointu, eventu, portu, zmiennej środowiskowej, roli lub maszyny stanów aktualizuje ten plik w tym samym PR do `bank-contract`, co zmiana `openapi/*.yaml`.** Repo aplikacji nigdy nie zmienia kontraktu samodzielnie — podbija submoduł `contract`.

Normatywne szczegóły HTTP są w `openapi/openapi.yaml`, normatywne schematy zdarzeń w `asyncapi/asyncapi.yaml`.
Ten dokument to mapa; OpenAPI i AsyncAPI to teren.

## 1. Mapa sieci (dev)

| Serwis | Host:port (compose) | Cel |
|---|---|---|
| core-api | `core-api:8080` / localhost:8080 | REST API `/api/v1`, actuator `/actuator` |
| customer-web | localhost:3000 | UI klienta |
| backoffice-web | localhost:3001 | UI operatora |
| clearing-sim | `clearing-sim:8090` / localhost:8090 | Symulator izby — tylko `/admin/*` i `/actuator` |
| notifications | `notifications:8091` / localhost:8091 | Tylko `/actuator` |
| redpanda | `redpanda:9092` (wewnątrz), localhost:19092 (z hosta) | Broker Kafka API |
| redpanda-console | localhost:8085 | Podgląd tematów, wiadomości, lagu |
| postgres | `postgres:5432` | Baza `bank` |
| keycloak | `keycloak:8081` / localhost:8081 | Realm `bank` |
| mailpit | SMTP `mailpit:1025`, UI localhost:8025 | Mail dev |

## 2. Tożsamość (realm Keycloak `bank`)

Klienci:

| Client id | Typ | Używany przez |
|---|---|---|
| `customer-web` | publiczny, PKCE | UI klienta |
| `backoffice-web` | publiczny, PKCE | UI operatora |
| `core-api` | bearer-only resource | walidacja tokenów |
| `clearing-sim` | — | nie wywołuje core-api; brak klienta Keycloak (admin HTTP bez auth w dev) |

Role realmu: `CUSTOMER`, `OPERATOR`, `ADMIN`.
Claimy tokenu, na których polega core-api: `sub` (mapuje na `customers.customer.keycloak_sub`), `realm_access.roles`, `email`.
Czas życia access tokenu 5 min, refresh 30 min. Użytkownicy testowi tworzeni przez `infra/keycloak/seed-users.sh`.

## 3. API HTTP core-api

Ścieżka bazowa `/api/v1`. Auth: `Authorization: Bearer <jwt>`. Żądania mutujące wymagają `Idempotency-Key` (UUID, unikalny per klient przez 24 h).

Konwencje:
- Kwoty: `{"minor": 12345, "currency": "PLN"}`.
- Daty: `YYYY-MM-DD`; chwile: RFC 3339 UTC.
- Błędy: `application/problem+json`, `type` to `https://bank.local/problems/<slug>`. Stabilne slugi:
  `validation`, `not-found`, `forbidden`, `insufficient-funds`, `limit-exceeded`, `duplicate-request`, `conflict`, `business-day-closed`, `invalid-iban`, `unbalanced-entry`.
- Paginacja: `?cursor=&limit=` → `{ "items": [], "nextCursor": "…|null" }`.

Grupy zasobów (tagi OpenAPI w nawiasach):

| Ścieżka | Role | Cel |
|---|---|---|
| `/me` [customer] | CUSTOMER | Własny profil klienta |
| `/me/accounts`, `/me/accounts/{id}`, `/me/accounts/{id}/transactions` [customer] | CUSTOMER | Własne rachunki i historia (odczyt księgi przez `accounts`) |
| `/me/payments`, `/me/payments/{id}`, `/me/payments/{id}/confirm` [customer] | CUSTOMER | Utworzenie przelewu, potwierdzenie kodem z e-maila, śledzenie statusu |
| `/me/standing-orders` [customer] | CUSTOMER | CRUD zleceń stałych |
| `/customers`, `/customers/{id}`, `/customers/{id}/accounts` [operator] | OPERATOR, ADMIN | Administracja klientami, otwieranie rachunków |
| `/accounts/{id}`, `/accounts/{id}/holds` [operator] | OPERATOR, ADMIN | Szczegóły rachunku, ręczne blokady |
| `/payments/{id}`, `/payments/{id}/return` [operator] | OPERATOR, ADMIN | Podgląd płatności, ręczny zwrot |
| `/ledger/gl-accounts`, `/ledger/entries`, `/ledger/entries/{id}/reverse`, `/ledger/entries:manual` [operator] | OPERATOR (odczyt), ADMIN (zapis) | Przeglądanie GL, ręczne księgowanie, storno |
| `/interest/rate-schedules` [operator] | ADMIN | Stopy produktów w czasie |
| `/business-days`, `/business-days/current`, `/business-days:close` [admin] | ADMIN | Kalendarz i wyzwalacz EOD |
| `/jobs`, `/jobs/{id}` [admin] | ADMIN | Przebiegi zadań batch |

`customer-web` może wołać tylko `[customer]`; `backoffice-web` tylko `[operator]`/`[admin]`. Żadna inna aplikacja nie woła core-api po HTTP.

### Cykl życia płatności (co klient widzi w `status`)

```
CREATED ──▶ PENDING_CONFIRMATION ──▶ POSTED ──▶ SETTLED
   │               │                    │
   └──▶ REJECTED ◀─┘ (walidacja,        └──▶ RETURNED  (zwrot z izby lub operatora; zaksięgowane storno)
                     wygasły kod)
```

- Przelewy wewnętrzne przechodzą `POSTED → SETTLED` natychmiast.
- Przelewy zewnętrzne zostają w `POSTED`, dopóki z szyny nie przyjdzie `clearing.settled` / `clearing.returned`.
- Saldo dostępne = saldo księgowe − suma aktywnych blokad. Blokada istnieje od `PENDING_CONFIRMATION` do `POSTED`/`REJECTED`.

### Stany rachunku

`ACTIVE → BLOCKED (operator) → ACTIVE`, `ACTIVE → CLOSED` (tylko gdy saldo = 0 i brak blokad). Księgowania na `CLOSED` są odrzucane; na `BLOCKED` dozwolone tylko uznania.

## 4. Szyna zdarzeń

Broker: Redpanda (Kafka API). Serializacja: JSON (UTF-8), jedna koperta dla wszystkich zdarzeń. Nagłówki Kafka: `type`, `version`, `correlationId` (duplikaty pól koperty — do filtrowania bez deserializacji). Klucz wiadomości: `aggregateId`.

### Koperta

```json
{
  "id": "uuid v7",
  "type": "payment.posted",
  "version": 1,
  "occurredAt": "2026-09-08T10:15:30Z",
  "businessDate": "2026-09-08",
  "producer": "core-api",
  "aggregateType": "Payment",
  "aggregateId": "uuid",
  "correlationId": "uuid",
  "causationId": "uuid | null",
  "payload": { }
}
```

`id` służy do deduplikacji w inboxie konsumenta. `causationId` = `id` zdarzenia, które wywołało to zdarzenie (np. `clearing.settled` → `payment.settled`), do śledzenia łańcuchów.

### Tematy

| Temat | Producent | Konsumenci | Retencja (dev) |
|---|---|---|---|
| `bank.customers.v1` | core-api | notifications | 7 dni |
| `bank.accounts.v1` | core-api | notifications | 7 dni |
| `bank.payments.v1` | core-api | notifications, clearing-sim | 7 dni |
| `bank.interest.v1` | core-api | notifications | 7 dni |
| `bank.batch.v1` | core-api | (dziś nikt zewnętrzny; Console) | 7 dni |
| `bank.clearing.v1` | clearing-sim | core-api (`payments`) | 7 dni |

Sufiks `.v1` to wersja *tematu*: zmienia się tylko przy niekompatybilnej zmianie koperty. Wersja *zdarzenia* jest w polu `version`. Tematy tworzy `bank-infra` (`make topics`), aplikacje ich nie tworzą. Grupy konsumentów: `<app>` (`notifications`, `clearing-sim`, `core-api-payments`).

### Katalog zdarzeń

| `type` | Temat | Payload (kluczowe pola) | Konsument i reakcja |
|---|---|---|---|
| `customer.created` | customers | customerId, email | notifications → mail powitalny |
| `account.opened` | accounts | accountId, customerId, iban, productCode | notifications → mail |
| `payment.confirmation_requested` | payments | paymentId, customerId, email, **code** (jawny), expiresAt | notifications → mail z kodem. Jedyny payload z sekretem; retencja tematu jest krótka, `core-api` trzyma tylko hash |
| `payment.posted` | payments | paymentId, kind, debtorAccountId, debtorIban, creditorIban, creditorName, amount, title, businessDate, **external:boolean** | notifications → mail; clearing-sim → jeśli `external` i `kind=EXTERNAL_OUT`, po opóźnieniu publikuje `clearing.settled`/`clearing.returned` |
| `payment.rejected` | payments | paymentId, reason | notifications |
| `payment.settled` | payments | paymentId, clearingRef | notifications |
| `payment.returned` | payments | paymentId, reasonCode, reversalEntryId | notifications |
| `payment.incoming_credited` | payments | paymentId, creditorAccountId, amount, debtorName, title | notifications |
| `interest.capitalized` | interest | accountId, customerId, gross, tax, net, periodStart, periodEnd | notifications |
| `businessday.closed` | batch | businessDate, nextBusinessDate, jobRunId | — (obserwacja) |
| `clearing.settled` | clearing | clearingRef, paymentId, settledAt | core-api → płatność `SETTLED`, publikuje `payment.settled` |
| `clearing.returned` | clearing | clearingRef, paymentId, reasonCode | core-api → storno, `RETURNED`, publikuje `payment.returned` |
| `clearing.incoming_received` | clearing | clearingRef, debtorIban, debtorName, creditorIban, amount, title, valueDate | core-api → jeśli IBAN znany i rachunek nie `CLOSED`: `TRANSFER_IN`, publikuje `payment.incoming_credited`; inaczej: nic nie księguje, publikuje `payment.incoming_rejected` (clearing-sim symuluje zwrot do nadawcy) |
| `payment.incoming_rejected` | payments | clearingRef, creditorIban, reasonCode | clearing-sim (log), notifications (nie) |

Kody powodu zwrotu (podzbiór ISO 20022): `AC01` błędny rachunek, `AC04` rachunek zamknięty, `AM04` brak środków (przez nas nigdy nie emitowany), `MS03` powód nieokreślony.

### Zasady dla producentów i konsumentów

- Producent: zdarzenie jest zapisem faktu, który już zaszedł w DB producenta. `core-api` publikuje wyłącznie przez outbox; `clearing-sim` może publikować bezpośrednio (nie ma stanu do ochrony).
- Konsument: idempotentny po `id` (inbox), toleruje duplikaty, nieznane `type`, nieznane pola i zmianę kolejności między agregatami. Błąd przetwarzania → retry z backoffem (3×), potem `bank.<domena>.v1.dlq` + alert; **nigdy** cicho pomijaj.
- Kolejność w obrębie `aggregateId` jest gwarantowana; konsument nie zakłada nic o kolejności między agregatami ani między tematami.
- Payload nie zawiera PII poza id, IBAN-em (potrzebny do routingu w izbie) i e-mailem tam, gdzie konsument wysyła wiadomość. Kwoty jako `{"minor","currency"}`.
- Zmiana kompatybilna = nowe opcjonalne pole lub nowy `type`. Niekompatybilna = `version+1`, producent publikuje obie wersje ≥ 2 tygodnie, konsumenci deklarują w AsyncAPI, którą czytają.

## 5. Izba rozliczeniowa (core-api ⇄ clearing-sim)

Cała wymiana idzie przez szynę — patrz §4: `payment.posted` (external) w jedną stronę, `clearing.*` w drugą. Żadnego HTTP między tymi aplikacjami.

Cykl przelewu zewnętrznego w zdarzeniach:

```
core-api:      payment.posted {external:true, paymentId}
clearing-sim:  (opóźnienie) clearing.settled {paymentId, clearingRef}   |  clearing.returned {paymentId, reasonCode}
core-api:      payment.settled                                            |  payment.returned  (+ storno w księdze)
```

Przelew przychodzący: `clearing.incoming_received` → `payment.incoming_credited` albo `payment.incoming_rejected`.

Idempotencja: `core-api` dedupuje po `id` koperty (inbox) **i** po `clearingRef` (unikalny w `payment`). `clearing-sim` dedupuje po `paymentId`.

### Admin clearing-sim (HTTP, tylko dev/testy, bez auth)

`POST http://localhost:8090/admin/incoming` — body jak payload `clearing.incoming_received`; sim publikuje zdarzenie.
`POST http://localhost:8090/admin/config` — `{ "settlementDelaySeconds": 10, "returnRatePercent": 5, "alwaysReturnIbans": ["PL…"] }`.
`POST http://localhost:8090/admin/traffic` — `{ "incomingPerMinute": 2, "targetIbans": ["PL…"] }` — generator ruchu przychodzącego (do „system żyje").

## 6. Zmienne środowiskowe

| Zmienna | Używa | Domyślnie (dev) |
|---|---|---|
| `DB_URL`, `DB_USER`, `DB_PASSWORD` | core-api | `jdbc:postgresql://postgres:5432/bank`, `bank`, `bank` |
| `KEYCLOAK_ISSUER_URI` | core-api, aplikacje web | `http://keycloak:8081/realms/bank` |
| `KAFKA_BOOTSTRAP_SERVERS` | core-api, clearing-sim, notifications | `redpanda:9092` |
| `KAFKA_GROUP_ID` | każdy konsument | nazwa aplikacji (`core-api-payments`, `notifications`, `clearing-sim`) |
| `CORE_API_URL` | aplikacje web | `http://core-api:8080` |
| `SMTP_HOST`, `SMTP_PORT` | notifications | `mailpit`, `1025` |
| `INBOX_DB_PATH` | notifications | `/data/inbox.sqlite` |
| `SPRING_PROFILES_ACTIVE` | core-api | `api,batch` |
| `BANK_CODE` | core-api | `10000000` (fikcyjny 8-cyfrowy numer rozliczeniowy) |
| `NEXT_PUBLIC_*` | aplikacje web | patrz `.env.example` każdej aplikacji |

## 7. Porty i wersje, których nie zmienia się po cichu

Porty z §1, ścieżka bazowa `/api/v1`, nazwy tematów, kształt koperty zdarzenia, slugi `type` błędów, nazwy ról i grup konsumentów. Zmiana którejkolwiek z tych rzeczy to ADR.

# ADR-007: Diagnostyka szyny (`/ops/*`) wystawiona z core-api przez Kafka AdminClient

- Status: Proponowany
- Data: 2026-09-23

## Kontekst
`backoffice-web` ma pokazywać stan szyny: lag grup konsumentów i wiadomości, które wylądowały w `bank.<domena>.v1.dlq`
(`integration-contracts.md` §4). Dziś jedynym miejscem, gdzie to widać, jest Redpanda Console — osobna aplikacja, osobne
logowanie, poza rolami realmu `bank`. Konsola operatora nie może rozmawiać z brokerem bezpośrednio (`CLAUDE.md` §5: UI nie
dotyka szyny, czyta stan przez REST), a szyną nie wolno zadać pytania — idą nią wyłącznie fakty, nigdy request-reply.
Zostaje odczyt przez REST z aplikacji, która i tak ma połączenie z brokerem.

## Decyzja
Wystaw `GET /api/v1/ops/consumers` i `GET /api/v1/ops/dlq` z `core-api`, `x-roles: [ADMIN]`, oba wyłącznie do odczytu.
Implementacja czyta Kafka `AdminClient`em (offsety grup, końce logów) i `Consumer`em bez zatwierdzania offsetów (podgląd
rekordów DLQ) — nie dotyka bazy banku i niczego nie publikuje. Brak ponawiania i kasowania z DLQ przez API: naprawa jest
decyzją człowieka i idzie przez Console albo przez ponowne wywołanie komendy. `payload` wiadomości DLQ wraca jako tekst,
bez deserializacji. Broker niedostępny → `503` `upstream-unavailable` (nowy slug; stan banku jest nienaruszony, żądanie
można powtórzyć). `/ops/*` jest diagnostyką, nie stanem banku — nie wchodzi do żadnego raportu ani uzgodnienia.

Odrzucone: własny mikroserwis „ops" (kolejna aplikacja i kolejny klient Keycloak dla dwóch odczytów); proxy do Redpanda
Console (i tak wymaga własnej auth, a Console nie ma stabilnego API); wystawianie tego przez `/actuator/health`
(health ma odpowiadać binarnie, a nie zwracać listy z paginacją); komenda na szynie pytająca o lag (zabronione — §5).

## Konsekwencje
+ Operacyjny obraz szyny w tych samych rolach i tym samym UI, co reszta konsoli; Console przestaje być obowiązkowa w dev.
+ Zero nowej infrastruktury: `core-api` ma już połączenie z brokerem i konfigurację `KAFKA_BOOTSTRAP_SERVERS`.
− `core-api` dostaje zależność operacyjną poza własną bazą: pierwszy endpoint, który może zwrócić `503` z powodu cudzej
  awarii. Dlatego osobny slug i jawne „bez wpływu na stan banku" w kontrakcie.
− `AdminClient` bywa wolny przy niedostępnym brokerze — implementacja musi mieć krótki timeout, żeby nie blokować wątków.
− Podgląd DLQ czyta treść zdarzeń; `payment.confirmation_requested` niesie jawny kod potwierdzenia, więc `/ops/dlq` jest
  tylko dla `ADMIN` i nie trafia do logów.
Zmienia `integration-contracts.md` §3 (nowa grupa zasobów i slug `upstream-unavailable`) oraz `openapi/openapi.yaml`.

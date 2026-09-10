# ADR-006: Szyna zdarzeń (Redpanda / Kafka API) jako jedyny kanał asynchroniczny między aplikacjami

- Status: Przyjęty
- Data: 2026-09-08

## Kontekst
Zespół ustalił, że system ma być zbudowany wokół szyny danych: aplikacje mają się dowiadywać o faktach przez zdarzenia, a nie przez wzajemne wywołania HTTP, i ma być możliwe dołączanie nowych konsumentów bez zmian w producencie. Wcześniejszy projekt (ADR-001…005) miał outbox i katalog zdarzeń, ale tylko w obrębie jednego procesu, a izba rozliczeniowa była integrowana przez REST.

## Decyzja
Broker: Redpanda (Kafka API, jeden kontener, Console do podglądu). `core-api` publikuje wyłącznie przez transactional outbox + relay w profilu `batch`; konsumuje tematy izby przez inbox. `notifications` wychodzi z `core-api` jako osobna aplikacja–konsument. `clearing-sim` przestaje wołać `core-api` po HTTP: konsumuje `payment.posted`, publikuje `clearing.*`. Katalog zdarzeń w `asyncapi/asyncapi.yaml` w `bank-contract`, koperta i tematy w kontraktach §4. Przez szynę idą wyłącznie fakty (zdarzenia), nigdy komendy ani request-reply. UI nadal po REST.

Odrzucone: NATS (mniej standardowy dla zespołu, mniejsza wartość edukacyjna), RabbitMQ (kolejki zamiast logu — brak replay), Debezium/CDC dla outboxa (kontener więcej, trudniejsze testy; relay z pollingiem wystarcza), schema registry (na start walidacja schematów w testach kontraktowych obu stron).

## Konsekwencje
+ Luźne sprzężenie: nowy konsument (wyciągi, analityka) to nowe repo i subskrypcja, zero zmian w `core-api`.
+ Log zdarzeń z retencją = replay i debugowanie przez Console; `correlationId` w kopercie daje śledzenie przelewu przez wszystkie aplikacje.
+ Awaria `notifications` lub `clearing-sim` nie zatrzymuje banku; zdarzenia czekają.
− Jeden kontener więcej, konsumenci muszą być idempotentni i tolerować duplikaty — inbox jest obowiązkowy.
− Spójność ostateczna: UI może zobaczyć `POSTED` sekundę przed mailem. Akceptowane; opcjonalnie SSE w etapie 9.
− Dwa kontrakty do utrzymania (OpenAPI + AsyncAPI); ten sam przepływ PR w `bank-contract`.
Zmienia `CLAUDE.md` §4–5, `architecture.md` §1–4a, `integration-contracts.md` §4–6. Zastępuje protokół HTTP izby z wcześniejszej wersji §5.

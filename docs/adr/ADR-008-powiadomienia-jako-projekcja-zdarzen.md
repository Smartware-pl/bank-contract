# ADR-008: `/me/notifications` jako projekcja zdarzeń w core-api (moduł `messaging`)

- Status: Proponowany
- Data: 2026-09-23

## Kontekst
`customer-web` ma mieć dzwonek z listą tego, co się klientowi wydarzyło: przelew rozliczony, zwrot, kapitalizacja,
odrzucone zlecenie. Te fakty już istnieją jako zdarzenia na szynie (`integration-contracts.md` §4) i już są konsumowane
przez `bank-notifications`, który wysyła z nich maile. Kuszące jest dołożenie REST do `bank-notifications`, ale to
złamałoby zasadę, że jedynym źródłem prawdy o stanie banku jest baza `core-api`, a UI czyta stan wyłącznie z `core-api`
(`CLAUDE.md` §5). Z drugiej strony powiadomienie nie należy do żadnego istniejącego modułu: powstaje ze zdarzeń
`payments`, `interest` i `accounts` naraz, a dokładanie go do `payments` zmusiłoby moduł księgujący do rozumienia
kapitalizacji i otwarcia rachunku.

## Decyzja
Powiadomienia w aplikacji są **projekcją odczytową w core-api**, nie nowym źródłem prawdy. Powstaje moduł `messaging`
z własnym schematem Postgresa i tabelą `customer_notification` (`domain-model.md` §3), który konsumuje zdarzenia domenowe
Spring Modulith z `payments`, `interest` i `accounts` i zapisuje z nich wiersze idempotentnie po `event_id`. Moduł
wystawia `GET /me/notifications` i `POST /me/notifications/{id}:read`; `type` powiadomienia to dokładnie `type` zdarzenia
z katalogu §4, a treść dla UI (`title`, `body`) jest budowana w `messaging`, nie w przeglądarce. Pełne dane są zawsze pod
`refs` przez zwykłe zasoby `/me/*` — powiadomienie nigdy nie jest jedynym miejscem, gdzie coś widać, i jego utrata nie
zmienia stanu banku. `bank-notifications` zostaje bez zmian: dalej wysyła maile, dalej nie ma REST-u.

Odrzucone: REST w `bank-notifications` (UI musiałoby wołać dwie aplikacje, a aplikacja bez księgi stałaby się źródłem
prawdy dla ekranu); tabela w `payments` (kapitalizacja i otwarcie rachunku nie są płatnościami); liczenie listy w locie
z historii i płatności przy każdym żądaniu (nie ma jak zapamiętać „przeczytane", a UI musiałby zgadywać, co jest nowe);
SSE/WebSocket zamiast tabeli (nie przetrwa przeładowania strony; ortogonalne — można dołożyć w etapie 9).

## Konsekwencje
+ UI klienta czyta wszystko z jednego API i jednego tokenu; dzwonek działa po przeładowaniu i na drugim urządzeniu.
+ `messaging` jest czystym konsumentem: nie księguje, nie zmienia agregatów, więc jego awaria nie dotyka pieniędzy.
+ Nowy typ zdarzenia = nowy wiersz projekcji bez zmian w `payments`/`interest`.
− Rośnie lista modułów w `CLAUDE.md` §5 (`common`, `customers`, `accounts`, `ledger`, `payments`, `interest`, `batch`,
  `outbox`, `audit` + `messaging`) — to zmiana konstytucji i dlatego ten ADR, a nie cicha decyzja w kodzie.
− Duplikacja treści z `bank-notifications` (ten sam fakt opisany dwa razy: mailem i w aplikacji). Akceptowane: kanały
  mają różne teksty i różne cykle życia; wspólny szablon wymagałby współdzielonej biblioteki między repozytoriami.
− Spójność ostateczna: dzwonek może zapalić się ułamek sekundy po tym, jak płatność pokaże się jako `SETTLED`.
Zmienia `CLAUDE.md` §5 (lista modułów), `domain-model.md` §3, `integration-contracts.md` §3 i `openapi/openapi.yaml`.

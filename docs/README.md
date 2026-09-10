# Indeks dokumentacji

| Plik | Czytaj, gdy |
|---|---|
| `architecture.md` | Potrzebujesz wiedzieć, która aplikacja co robi, listę modułów, roadmapę i Definition of Done per etap |
| `integration-contracts.md` | Dotykasz czegoś, co przekracza granicę aplikacji lub modułu: HTTP, tematy i zdarzenia na szynie, zmienne środowiskowe, porty, role |
| `domain-model.md` | Dodajesz lub zmieniasz encję, stan, termin lub konto GL |
| `business-rules.md` | Dotykasz pieniędzy, odsetek, EOD, limitów, IBAN, storn |
| `adr/` | Podejmujesz lub kwestionujesz decyzję strukturalną |
| `reference/` | Fixture'y testowe utrzymywane ręcznie (przypadki odsetkowe) |

Zasada: docs, `openapi/` i `asyncapi/` zmieniają się w tym samym PR do `bank-contract`. Repo aplikacji, które implementuje nowy endpoint bez wcześniejszego PR tutaj, łamie kontrakt.

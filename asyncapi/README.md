# asyncapi

`asyncapi.yaml` (AsyncAPI 3.0) — normatywny opis szyny: serwer (Redpanda), kanały = tematy `bank.*.v1`, operacje
send/receive per aplikacja (z grupą konsumentów w bindingu Kafka), wiadomości per `type`.

Układ plików (JSON Schema draft 2020-12, normatywne):

| Plik | Co zawiera |
|---|---|
| `schemas/envelope.json` | wspólna koperta (`EventEnvelope`); `payload` to obiekt, którego kształt zależy od `type` |
| `schemas/money.json` | `Money {minor, currency}` |
| `schemas/kafka-headers.json` | nagłówki Kafka `type`, `version`, `correlationId` |
| `schemas/payloads/<type>.json` | schemat payloadu danego zdarzenia (`<Type>Payload`) — z tego generują się klasy Java |
| `schemas/events/<type>.json` | pełne zdarzenie = koperta + `type`/`version`/`producer`/`aggregateType` jako `const` + payload; używane w testach kontraktowych |
| `examples/<type>.json` | jeden poprawny przykład na zdarzenie; każda aplikacja waliduje je w testach kontraktowych |
| `tools/generate.py` | generator powyższych plików z jednej tabeli zdarzeń — zmiana zdarzenia = edycja skryptu + uruchomienie + commit wyników |

Generacja w repo konsumujących, z submodułu `contract/`:
- core-api, clearing-sim, notifications: `jsonschema2pojo` (Gradle) z `schemas/envelope.json`, `schemas/money.json`
  i `schemas/payloads/` (`useTitleAsClassname`), pakiet `pl.smartware.bank.contract.events`; koperta ma `payload: JsonNode`,
  konsument po `type` robi `treeToValue(payload, <Type>Payload.class)`.
- Test kontraktowy w każdej aplikacji: każdy plik z `examples/` waliduje się względem `schemas/events/<type>.json`
  i deserializuje do wygenerowanych klas bez błędu.

Zasady: patrz `docs/integration-contracts.md` §4. Zmiana tu = zmiana tabeli katalogu zdarzeń w tym samym PR.
Pola tylko dodajesz (opcjonalne); usunięcie lub zmiana znaczenia = `version + 1` i równoległa publikacja obu wersji.

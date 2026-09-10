# asyncapi

`asyncapi.yaml` (AsyncAPI 3.x) — normatywny opis szyny: serwery (Redpanda), kanały = tematy `bank.*.v1`, operacje send/receive per aplikacja, schemat koperty i schematy payloadów per `type`.

Generacja w repo konsumujących, z submodułu `contract/`:
- core-api, clearing-sim, notifications: klasy koperty i payloadów z osadzonych JSON Schema (`jsonschema2pojo` przez Gradle), walidacja przykładowych wiadomości w testach kontraktowych (`asyncapi/examples/*.json`).

Zasady: patrz `docs/integration-contracts.md` §4. Zmiana tu = zmiana tabeli katalogu zdarzeń w tym samym PR.

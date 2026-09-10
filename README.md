# bank-contract

Wspólne repo projektu: konstytucja dla Claude Code (`CLAUDE.md`), dokumentacja (`docs/`), kontrakt HTTP (`openapi/`) i kontrakt zdarzeń (`asyncapi/`).
Każde repo aplikacji ma to repo jako submoduł w `contract/`.

Zasady:
- Każdy PR wymaga review drugiej osoby (CODEOWNERS: `* @jacek @kolega`).
- `openapi/*.yaml`, `asyncapi/asyncapi.yaml` i `docs/integration-contracts.md` zmieniają się w tym samym PR.
- Zmiany w `/api/v1` i w zdarzeniach `version: 1` są addytywne. Łamiące → `/api/v2` lub `version: 2` + ADR.
- Tag `contract-vX.Y` po każdym merge, który zmienia OpenAPI lub AsyncAPI — repo aplikacji podbijają submoduł do tagu, nie do losowego commita.

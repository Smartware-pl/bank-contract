# openapi

- `openapi.yaml` — core-api `/api/v1`. Tagi: `customer`, `operator`, `admin`, `internal`.

Generacja odbywa się w repo konsumujących, z submodułu `contract/`:
- web: `openapi-typescript` + `openapi-fetch` → `src/generated/`
- core-api: Gradle `openApiGenerate` (`spring`, `interfaceOnly=true`) → `build/generated/`

Wygenerowany kod nie jest commitowany.

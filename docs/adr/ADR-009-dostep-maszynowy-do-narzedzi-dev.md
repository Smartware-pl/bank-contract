# ADR-009: Dostęp z zewnątrz do narzędzi dev na AWS — OIDC dla ludzi, client credentials + bramka JWT dla maszyn, szyna tylko do odczytu

- Status: Proponowany
- Data: 2026-09-28

## Kontekst
Zestaw e2e w `bank-infra/e2e` (Playwright + BDD; scenariusze w `e2e/features/*.feature` są też w Jirze i nie zmieniają się)
ma dać się uruchomić **z zewnątrz** — z laptopa testera i z runnera STS poza AWS — przeciwko środowisku dev na AWS.
UI, core-api i Keycloak są tam już publiczne (`https://app|office|api|auth.bank-dev.smart-env.pl`) i chronione tokenami
realmu `bank` (`integration-contracts.md` §2). Testy potrzebują jednak także narzędzi, które **nie mają własnego logowania**:

- Mailpit REST (odczyt kodów potwierdzeń z maili),
- `clearing-sim` `/admin/*` (sterowanie izbą — `integration-contracts.md` §5, „bez auth" w compose),
- `notifications` `/actuator/health`,
- odczytu zdarzeń z tematów `bank.*.v1` (asercje „zdarzenie opublikowane").

Na AWS te narzędzia są w VPC albo (bank-infra#23) za regułą ALB `authenticate-oidc` wymagającą roli `STAFF_TOOLS` —
to działa dla człowieka z przeglądarką, ale nie dla procesu testowego, który nie przejdzie interaktywnego logowania.
Szyna (Kafka API) nie jest wystawiona wcale. Obowiązuje zasada, że dostęp do dev z zewnątrz opiera się wyłącznie na
tożsamości z Keycloaka (OIDC) — bez długożyjących kluczy AWS na maszynach ludzi i runnerów.

Brakuje więc kategorii, której dziś nie ma w stacku (`CLAUDE.md` §4 wymaga na nią ADR): **bramki uwierzytelniającej**
(proxy weryfikujące JWT przed narzędziami bez własnego logowania) oraz **publicznego odczytu szyny przez HTTP**
(Redpanda HTTP Proxy).

## Decyzja
Tylko na środowisku dev na AWS rozdziel dostęp do narzędzi na dwie ścieżki.

**Ludzie**: przeglądarka przez ALB `authenticate-oidc` do realmu `bank`, wymagana rola realmu `STAFF_TOOLS` (klient
`staff-tools`, bank-infra#23) — bez zmian.

**Maszyny**: poufny klient `e2e-runner` w realmie `bank` — wyłącznie grant `client_credentials` (service account, bez
innych grantów); konto serwisowe ma rolę realmu `STAFF_TOOLS`, mapper audience dodaje `aud` = `staff-tools-gateway`;
sekret w Secrets Manager `/bank/dev/keycloak/e2e-runner-client`. Harness pobiera token
(`POST {issuer}/protocol/openid-connect/token`, `grant_type=client_credentials`), trzyma go w pamięci do `exp − 30 s` i
dokłada `Authorization: Bearer <jwt>` do każdego wywołania Mailpit, izby, notifications i szyny. Na ALB reguła o wyższym
priorytecie niż OIDC (host ∈ `izba.`, `mail.`, `powiadomienia.`, `szyna.bank-dev.smart-env.pl` **i** nagłówek
`Authorization` = `Bearer *`) kieruje żądanie do bramki, która **sama** weryfikuje JWT — podpis kluczami JWKS realmu,
`iss` = issuer realmu `bank`, `aud` zawiera `staff-tools-gateway`, `exp` — i wymaga `STAFF_TOOLS` w
`realm_access.roles`. Brak lub nieważny token → `401`, brak roli lub audience → `403`; nigdy przekazanie dalej. Sama
obecność nagłówka niczego nie otwiera: reguła ALB tylko wybiera ścieżkę, decyzję podejmuje bramka.

**Szyna**: wystawiona wyłącznie przez Redpanda HTTP Proxy (REST API v2) pod `szyna.bank-dev.smart-env.pl` i wyłącznie do
odczytu — `POST` na `/topics/*` (produce) jest blokowany (`403`) na ALB i/lub w bramce; dozwolone są tylko operacje
konsumenta potrzebne do odczytu. Harness w trybie zdalnym czyta szynę przez `E2E_KAFKA_HTTP_URL` zamiast
`E2E_KAFKA_BROKERS`.

Nic z tego nie istnieje w lokalnym compose ani poza dev: bez zmiennych trybu zdalnego harness zachowuje się dokładnie
jak dziś.

## Odrzucone alternatywy
- **Statyczny klucz w nagłówku** (np. `X-Api-Key` porównywany przez regułę ALB) — odrzucony w przeglądzie
  bezpieczeństwa: długożyjący sekret bez tożsamości, bez wygasania i bez roli; wyciek = trwały dostęp do izby i maili do
  czasu ręcznej rotacji.
- **VPN / AWS SSM port forwarding** — wymaga kluczy AWS (lub sesji IAM) na laptopie testera i na runnerze STS, co łamie
  zasadę dostępu do dev wyłącznie przez tożsamość z Keycloaka; do tego dodatkowy klient na każdej maszynie.
- **Publiczne wystawienie brokera Kafka** — protokół binarny, którego ALB nie terminuje; broker w dev nie ma
  uwierzytelniania (SASL/mTLS to nowa konfiguracja wszystkich producentów i konsumentów), a dostęp natywny daje też
  produce, czyli możliwość wstrzyknięcia fałszywych faktów na szynę.
- **Runner w VPC** (self-hosted runner lub zadanie w ECS) — nie spełnia wymagania: testy mają iść z laptopa testera i z
  runnera STS poza AWS.

## Konsekwencje
+ Jeden model tożsamości dla ludzi i maszyn: realm `bank`, rola `STAFF_TOOLS`, krótkotrwały podpisany token (5 min,
  §2 kontraktów) zamiast współdzielonego sekretu w nagłówku. Odebranie dostępu = wyłączenie klienta lub roli w Keycloaku.
+ Scenariusze e2e się nie zmieniają; tryb zdalny to wyłącznie zmienne środowiskowe harnessu.
+ Aplikacje banku (core-api, clearing-sim, notifications, web) nie zmieniają się: nie znają `STAFF_TOOLS` ani bramki.
− Nowa ruchoma część w dev na AWS: bramka JWT (jej dostępność warunkuje e2e z zewnątrz) i Redpanda HTTP Proxy
  wystawione przez ALB.
− Sekret klienta `e2e-runner` jest nadal sekretem (Secrets Manager, zmienna harnessu `E2E_TOOLS_CLIENT_SECRET`): wymaga
  rotacji i nigdy nie trafia do gita (`CLAUDE.md` §5). Wyciek daje jednak tylko tokeny z rolą `STAFF_TOOLS` — bez
  dostępu do API banku w rolach `CUSTOMER`/`OPERATOR`/`ADMIN`.
− Odczyt szyny i Mailpit z zewnątrz ujawnia treść zdarzeń i maili, w tym jawny kod `payment.confirmation_requested` (to
  właśnie jest potrzebne testom) — dlatego tylko dev, tylko z rolą `STAFF_TOOLS`, tylko odczyt szyny, a bramka nie
  loguje treści żądań ani odpowiedzi.
− Reguły ALB (priorytet ścieżki maszynowej nad OIDC, blokada produce) stają się częścią zabezpieczeń — zmiana ich
  kolejności lub warunków wymaga przeglądu.

Zmienia `integration-contracts.md` §2 (klienci `staff-tools` i `e2e-runner`, rola `STAFF_TOOLS`), §5 (admin izby na dev
AWS za bramką) i §6 (nota o zmiennych harnessu `E2E_*`). Nie zmienia `openapi/` ani `asyncapi/`: bramka niczego nie
dodaje do API banku ani do katalogu zdarzeń. Infrastruktura (ALB, bramka, HTTP Proxy, klienci realmu) należy do
`bank-infra`.

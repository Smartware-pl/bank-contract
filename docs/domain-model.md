# Model domeny

Wspólny język dla całego repo. Kod używa terminu angielskiego; polskie odpowiedniki są tutaj, żeby UI operatora i testy używały spójnego słownictwa.

## 1. Słownik

| Angielski (kod) | Polski (UI) | Znaczenie |
|---|---|---|
| Customer | Klient | Osoba posiadająca rachunki. Jeden użytkownik Keycloak ↔ jeden klient. |
| Product | Produkt | Definicja typu rachunku: `CURRENT` (ROR), `SAVINGS` (konto oszczędnościowe). Niesie domyślny harmonogram stóp, dozwolone operacje, flagę debetu. |
| Account | Rachunek | Rachunek klienta z IBAN-em, produktem, stanem i subkontem GL. |
| IBAN / NRB | Numer rachunku | 28 znaków: `PL` + 26-cyfrowy NRB. Numer rozliczeniowy banku to `BANK_CODE`. Cyfry kontrolne wg ISO 7064 mod 97-10. |
| GL account | Konto księgowe | Węzeł planu kont. Rachunki klientów mapują się 1:1 na subkonta GL pod kontem kontrolnym zobowiązań wobec klientów. |
| Journal entry | Zapis księgowy / dekret | Jedno atomowe zdarzenie księgowe; ≥2 postingi sumujące się do zera. |
| Posting | Pozycja zapisu | Kwota ze znakiem na jednym koncie GL. Dodatnia = debet (Wn), ujemna = kredyt (Ma) — jedna kolumna ze znakiem, bez enuma dr/cr. |
| Reversal (storno) | Storno | Nowy zapis z odwróconymi postingami wskazujący na oryginał. |
| Balance | Saldo | Suma postingów na subkoncie GL rachunku do danej daty biznesowej. |
| Available balance | Saldo dostępne | Saldo − aktywne blokady (+ limit debetu, jeśli produkt pozwala). |
| Hold | Blokada | Tymczasowa rezerwacja środków powiązana z oczekującą płatnością lub akcją operatora. |
| Payment | Płatność / przelew | Żądanie przesunięcia pieniędzy. Wewnętrzny (oba IBAN-y w tym banku) lub zewnętrzny (przez izbę). |
| Standing order | Zlecenie stałe | Szablon płatności cyklicznej z harmonogramem. |
| Clearing | Rozliczenie międzybankowe | Zewnętrzna sieć rozliczeniowa; symulowana przez `clearing-sim`, komunikacja przez szynę. |
| Event bus | Szyna zdarzeń | Redpanda (Kafka API); jedyny kanał asynchroniczny między aplikacjami. |
| Outbox / inbox | Skrzynka nadawcza / odbiorcza | Wzorce zapewniające, że publikacja jest atomowa ze zmianą stanu (outbox) i że konsumpcja jest idempotentna (inbox). |
| Nostro (clearing) account | Rachunek nostro | Konto aktywów GL reprezentujące należności/zobowiązania wobec izby rozliczeniowej. |
| Business date | Data księgowa / dzień roboczy | Bieżący dzień księgowy banku; przesuwany tylko przez EOD. |
| Booking date | Data księgowania | Data biznesowa, pod którą zapis został zarejestrowany. |
| Value date | Data waluty | Data, od której kwota jest oprocentowana. |
| EOD (end of day) | Zamknięcie dnia | Batch zamykający datę biznesową: naliczenia, kapitalizacja, zlecenia stałe, uzgodnienie. |
| Accrual | Naliczenie odsetek | Dzienne odsetki wyliczone i zaksięgowane jako zobowiązanie/koszt, jeszcze nie wypłacone klientowi. |
| Capitalization | Kapitalizacja | Przeniesienie naliczonych odsetek na rachunek klienta (netto po podatku). |
| Withholding tax (Belka) | Podatek Belki | 19% zryczałtowany podatek od zysków kapitałowych, księgowany przy kapitalizacji. |
| Rate schedule | Harmonogram stóp | Progowe stopy procentowe per produkt, z datą obowiązywania. |

## 2. Plan kont (minimum)

| Kod | Nazwa | Typ | Uwagi |
|---|---|---|---|
| `1000` | Kasa / nostro izby rozliczeniowej | Aktywa | Przeciwstrona dla płatności zewnętrznych |
| `2000` | Depozyty klientów (kontrolne) | Zobowiązania | Rodzic wszystkich subkont klientów `2000-<accountId>` |
| `2100` | Odsetki naliczone do zapłaty | Zobowiązania | Uznawane przez dzienne naliczenie |
| `2200` | Podatek do zapłaty | Zobowiązania | Uznawane przy kapitalizacji |
| `2300` | Nieprzypisane wpływy | Zobowiązania | Pieniądze przychodzące z izby czekające na dopasowanie rachunku (po EOD ma być zero) |
| `4000` | Koszt odsetkowy | Koszty | Obciążane przez dzienne naliczenie |
| `4100` | Przychód z odsetek debetowych | Przychody | Dla produktów z saldem ujemnym |
| `4200` | Przychód z opłat | Przychody | Etap 8 |
| `9000` | Konto techniczne (suspense) | — | Parking dla korekt ręcznych; na EOD musi być zero |

Niezmiennik: `Σ Aktywa − Σ Zobowiązania − (Σ Przychody − Σ Koszty) = 0`, co jest równoważne z sumą wszystkich postingów równą zero.

## 3. Encje per moduł (tylko kluczowe pola)

**customers**
- `customer(id, keycloak_sub UNIQUE, email, full_name, status[ACTIVE|BLOCKED|CLOSED], version, created_at)`

**accounts**
- `product(code PK, name, kind[CURRENT|SAVINGS], allows_debit, allows_overdraft, overdraft_limit_minor, capitalization[MONTHLY|QUARTERLY|NONE], default_rate_schedule_id)`
- `account(id, customer_id, product_code, iban UNIQUE, gl_account_code, currency, status, opened_on, closed_on, version)`
- `account_hold(id, account_id, amount_minor, currency, reason, reference_type, reference_id, created_at, released_at)`

**ledger**
- `gl_account(code PK, name, type, parent_code, customer_account_id NULL)`
- `journal_entry(id, type, booking_date, value_date, business_date, idempotency_key UNIQUE, reference_type, reference_id, reversal_of NULL, description, created_at)`
- `posting(id, entry_id, gl_account_code, amount_minor ze znakiem, currency)`
- `balance_snapshot(gl_account_code, business_date, balance_minor, PK(code,date))`

**payments**
- `payment(id, kind[INTERNAL|EXTERNAL_OUT|EXTERNAL_IN], status, debtor_account_id NULL, creditor_account_id NULL, debtor_iban, creditor_iban, creditor_name, amount_minor, currency, title, requested_date, hold_id, entry_id, reversal_entry_id, clearing_ref, reason_code, idempotency_key, version, created_at, posted_at, settled_at)`
- `payment_confirmation(payment_id, code_hash, expires_at, attempts)`
- `standing_order(id, customer_id, debtor_account_id, creditor_iban, creditor_name, amount_minor, currency, title, frequency[MONTHLY|WEEKLY], day_of_period, next_run_date, status)`

**interest**
- `rate_schedule(id, product_code, effective_from, tiers JSONB [{upToMinor|null, annualRateBp}], day_count[ACT_365], created_at)`
- `accrual_daily(account_id, business_date, balance_minor, annual_rate_bp, accrued_minor, entry_id, PK(account_id,date))`
- `capitalization_run(id, account_id, period_start, period_end, gross_minor, tax_minor, net_minor, entry_id)`

**batch**
- `business_day(date PK, status[OPEN|CLOSING|CLOSED], opened_at, closed_at)`
- `job_run(id, job_name, business_date, status, started_at, finished_at, error, items_processed)`

**outbox** (core-api)
- `outbox(id, type, version, topic, partition_key, aggregate_type, aggregate_id, correlation_id, causation_id NULL, business_date, payload JSONB, occurred_at, published_at NULL, attempts)`
- `inbox(event_id PK, type, consumer_group, received_at, processed_at, outcome)`

**notifications** (osobna aplikacja, własna baza SQLite)
- `inbox(event_id PK, type, processed_at)`
- `notification(id, event_id, customer_id, channel[EMAIL], template, sent_at, status)`

**audit**
- `audit_log(id, actor_sub, actor_roles, command, aggregate_type, aggregate_id, correlation_id, outcome, at)`

## 4. Maszyny stanów

Płatność: patrz `integration-contracts.md` §3. Rachunek: `ACTIVE ⇄ BLOCKED`, `ACTIVE → CLOSED`. Dzień roboczy: `OPEN → CLOSING → CLOSED` (następny dzień `OPEN` powstaje w tej samej transakcji, która ustawia `CLOSED`). Klient: `ACTIVE ⇄ BLOCKED`, `→ CLOSED` tylko gdy wszystkie rachunki `CLOSED`.

## 5. Identyfikatory

UUID v7 dla wszystkich id encji (uporządkowane czasowo). Referencje dla ludzi: `PAY-<yyyymmdd>-<6 base32>`, `CLR-<yyyy>-<6 cyfr>`, `JE-<sekwencja>`. IBAN nigdy nie jest kluczem wewnętrznym.

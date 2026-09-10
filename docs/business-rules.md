# Reguły biznesowe

Reguły, które decydują o liczbach. Każda reguła tutaj ma (albo musi dostać) test. Kwoty w groszach, jeśli nie zaznaczono inaczej.

## 1. Pieniądze i zaokrąglanie

- Arytmetyka wewnętrzna na `long` w groszach. Kalkulator odsetek używa `BigDecimal` z `MathContext(20)` i zaokrągla `HALF_EVEN` do groszy dokładnie raz, na końcu dziennego naliczenia dla jednego rachunku.
- Nigdy nie zaokrąglaj pośrednich wyników progów osobno; sumuj progi w `BigDecimal`, zaokrąglij sumę.

## 2. Generowanie IBAN / NRB

- NRB = 2 cyfry kontrolne + 8-cyfrowy numer rozliczeniowy (`BANK_CODE`) + 16-cyfrowy numer rachunku.
- Numer rachunku = 16-cyfrowa sekwencja z zerami wiodącymi z `accounts.account_number_seq` (od 1). Bez zakodowanego znaczenia.
- Cyfry kontrolne: ISO 7064 mod 97-10 nad `bank_code + account_number + "2521"` („PL00" → litery na cyfry), IBAN = `PL` + kontrolne + NRB.
- Walidacja na wejściu: długość 28, prefiks `PL`, mod 97 == 1. Zagraniczne IBAN-y akceptowane składniowo (długość wg tabeli krajów), ale tylko jako odbiorcy płatności zewnętrznych.

## 3. Salda i blokady

- `balance(account, date)` = Σ postingów na subkoncie GL rachunku z `business_date ≤ date`. Konwencja znaku: saldo kredytowe subkonta zobowiązań jest pokazywane klientowi jako dodatnie. Moduł `accounts` odwraca znak przy prezentacji.
- `available = balance − Σ aktywnych blokad + overdraft_limit (jeśli product.allows_overdraft)`.
- Płatność jest przyjmowana tylko gdy `available ≥ amount` przy utworzeniu *i* przy księgowaniu (ponowne sprawdzenie pod blokadą wiersza).
- Blokady wygasają wraz z oknem potwierdzenia (15 min) → płatność `REJECTED`, blokada zwolniona.

## 4. Płatności

- Minimalna kwota 1 grosz; maksymalna per płatność 100 000,00 PLN (limit na poziomie produktu później).
- Limit dzienny per klient 200 000,00 PLN łącznie dla płatności `POSTED` z dzisiejszą datą biznesową.
- Potwierdzenie: 6-cyfrowy kod numeryczny wysyłany e-mailem; przechowywany jako SHA-256; 3 próby; ważny 15 min.
- Księgowanie przelewu wewnętrznego (jeden zapis, typ `TRANSFER`):
  - Wn `2000-<nadawca>` kwota, Ma `2000-<odbiorca>` kwota.
- Zewnętrzny wychodzący (typ `TRANSFER_OUT`): Wn `2000-<nadawca>`, Ma `1000`.
- Zwrot zewnętrzny (typ `REVERSAL`): odwrócone postingi oryginału, ustawione `reversal_of`, płatność → `RETURNED`.
- Zewnętrzny przychodzący (typ `TRANSFER_IN`): Wn `1000`, Ma `2000-<odbiorca>`. Nieznany IBAN → nic nie księgujemy, `422` do sim.
- Księgowania na rachunek `CLOSED` są odrzucane; `BLOCKED` przyjmuje tylko uznania.
- Płatności zlecone, gdy dzień roboczy nie jest `OPEN`, dostają problem `business-day-closed` (UI powinno pokazać „trwa zamknięcie dnia, spróbuj za chwilę").
- Reguły statusu rachunku (`CLOSED` odrzuca, `BLOCKED` tylko uznania) i sprawdzenie salda dostępnego obowiązują wyłącznie w module `payments` (przelewy, zlecenia stałe, uznania z izby). Moduł `ledger` ich nie zna: zapisy `MANUAL` i `REVERSAL` (ADMIN) mogą obciążyć `2000-*` poniżej zera i dotyczyć rachunku `BLOCKED`/`CLOSED` — dlatego wymagają `reason` i są oflagowane w audycie (§9).

## 5. Zlecenia stałe

- Wykonywane przez EOD dnia *poprzedzającego* `next_run_date`, tak by pieniądze ruszyły na początku dnia wykonania (księgowane z `business_date = next_run_date`). Jeśli dzień wykonania nie jest dniem roboczym, użyj następnego dnia roboczego.
- Niepowodzenie (brak środków) → płatność `REJECTED`, powiadomienie, `next_run_date` mimo to przesuwa się dalej.
- Bez kodu potwierdzenia (potwierdzone przy utworzeniu).

## 6. Kalendarz biznesowy i EOD

- Kalendarz zasiany 5 lat naprzód: pn–pt otwarte, sb/nd zamknięte, polskie święta państwowe zamknięte (stała lista + wyliczane od Wielkanocy).
- W każdej chwili dokładnie jeden `business_day` jest `OPEN`. `businessDate()` go zwraca.
- EOD (`POST /business-days:close` lub scheduler 23:00 Europe/Warsaw) działa jako uporządkowany łańcuch zadań; każdy krok jest idempotentny i logowany w `job_run`:
  1. `OPEN → CLOSING` (nowe księgowania odrzucane z `business-day-closed`; jedyny wyjątek: korekty ADMIN z §9 po nieudanym przebiegu).
  2. Wygaszenie przeterminowanych potwierdzeń.
  3. Wykonanie zleceń stałych przypadających na następny dzień roboczy.
  4. Dzienne naliczenie odsetek (§7) dla każdego oprocentowanego rachunku `ACTIVE`/`BLOCKED`.
  5. Kapitalizacja, jeśli dziś jest ostatni dzień kalendarzowy okresu produktu (§8).
  6. Snapshoty sald dla wszystkich kont GL; uzgodnienie: Σ snapshotów wg typu musi spełniać niezmiennik GL, `2300` i `9000` muszą być zerowe, Σ `2000-*` = `2000`. Niepowodzenie → zadanie `FAILED` z typowanym wynikiem uzgodnienia (`reconciliation`: kontrole `GL_INVARIANT`, `UNASSIGNED_INCOMING_ZERO`, `SUSPENSE_ZERO`, `CUSTOMER_CONTROL` z różnicą), dzień zostaje `CLOSING`, alert. Nigdy nie naprawiaj automatycznie; scheduler nie wznawia. ADMIN koryguje księgę (zapis ręczny lub storno — dozwolone w tym stanie, `business_date` = dzień `CLOSING`) i ponawia `POST /business-days:close`: powstaje nowy przebieg orkiestratora z `resumes_run_id`, kroki już `SUCCEEDED` dla tej daty są pomijane (są idempotentne), łańcuch startuje od nieudanego kroku. Korekta na `2000-*` po kroku 4 nie przelicza naliczenia za ten dzień — ma skutek odsetkowy od następnego dnia.
  7. `CLOSING → CLOSED`, następny dzień roboczy z kalendarza → `OPEN`.
- Przewijanie dev/test: `POST /business-days:close?times=N` (ADMIN, tylko gdy `bank.allow-fast-forward=true`).

## 7. Dzienne naliczanie odsetek

- Konwencja dni `ACT/365` (365 także w roku przestępnym — uproszczenie, udokumentowane).
- Użyte saldo: saldo księgowe na koniec dnia (blokady ignorowane).
- Stopa: harmonogram obowiązujący w `business_date`; progi działają marginalnie (pierwszy próg do `upToMinor`, następny dla nadwyżki). Stopy przechowywane w punktach bazowych.
- `accrued = Σ_progów saldoProgu × rateBp / 10 000 / 365`, zaokrąglone raz.
- Saldo dodatnie, `accrued > 0` → zapis `INTEREST_ACCRUAL`: Wn `4000`, Ma `2100`, oba na `accrued`, `reference = accrual_daily`.
- Saldo ujemne na produkcie z debetem → zapis `OVERDRAFT_ACCRUAL`: Wn `1300 Naliczone odsetki debetowe do otrzymania`, Ma `4100`. Konto GL `1300` dodajemy do planu kont przy implementacji debetu (etap 8); przy kapitalizacji należność rozliczana jest z rachunkiem klienta (Wn `2000-<rachunek>`, Ma `1300`).
- Naliczenie zerowe (saldo 0 lub stopa 0) → wiersz w `accrual_daily` z 0, bez zapisu księgowego.
- Dni zamknięte (weekendy/święta) też naliczają: EOD piątku księguje trzy wiersze naliczeń (pt, sb, nd) z odpowiednimi datami — dzięki temu „naliczenie za dzień kalendarzowy" zachodzi, choć EOD działa per dzień roboczy.

## 8. Kapitalizacja

- Okres = miesiąc kalendarzowy (`MONTHLY`) lub kwartał; uruchamiana w EOD, którego zakres kalendarzowy obejmuje ostatni dzień okresu.
- `gross = Σ accrued_minor` w okresie dla rachunku (z `accrual_daily`, nie przeliczane od nowa).
- `tax = round_HALF_EVEN(gross × 19%)` w groszach (uproszczenie: bez zaokrąglania podstawy do pełnych złotych).
- `net = gross − tax`. Jeden zapis `CAPITALIZATION`: Wn `2100` gross, Ma `2000-<rachunek>` net, Ma `2200` tax.
- Zamknięcie rachunku (`ACTIVE → CLOSED`) w jednej transakcji, w kolejności: (1) brak aktywnych blokad, inaczej `409` `conflict`; (2) jeśli Σ `accrual_daily.accrued_minor` od ostatniej kapitalizacji > 0 — zapis `CAPITALIZATION` tą samą regułą (wymaga dnia `OPEN`, inaczej `422` `business-day-closed`); (3) dopiero potem saldo musi być 0 — saldo ≠ 0 → `409` `conflict` z `extensions.balance`, rachunek zostaje `ACTIVE`, kapitalizacja pozostaje zaksięgowana, operator przenosi środki i powtarza.

## 9. Storna i korekty

- ADMIN może wystornować dowolny zapis poza dwoma przypadkami: zapis już wystornowany i zapis sam będący `REVERSAL` (oba → `409` `conflict`; zapis ma co najwyżej jedno storno). Powstaje `REVERSAL` z tymi samymi kontami i odwróconym znakiem kwot, `reversal_of` = oryginał, `booking_date` = `value_date` = `business_date` = bieżący dzień; oryginał pozostaje nietknięty.
- Storno z `/ledger/entries/{id}/reverse` jest wyłącznie księgowe: nie zmienia statusu płatności, blokad, `accrual_daily` ani `capitalization_run`. Zapisów z `reference_type = PAYMENT` nie stornuje się tą drogą (`409` `conflict`) — wyłącznie przez `POST /payments/{id}/return`, który utrzymuje maszynę stanów płatności spójną z księgą; to jedyne storno dostępne dla OPERATOR i dotyczy tylko płatności `POSTED`.
- Zapisy ręczne (ADMIN) muszą się bilansować, nie mogą dotykać `2000-*` bez udokumentowanego powodu i są oflagowane w audycie.
- Bez datowania wstecz: `business_date` każdego nowego zapisu równa się bieżącemu dniu `OPEN`, z wyjątkiem zadań EOD oraz korekt ADMIN (zapis ręczny, storno) w dniu `CLOSING` po nieudanym przebiegu EOD (§6) — te księgują w dzień `CLOSING`.

## 10. Dane referencyjne do testów

`docs/reference/interest-cases.csv` — kolumny: przypadek, produkt, saldo otwarcia, harmonogram stóp, dni, oczekiwane naliczenie dzienne, oczekiwane gross/tax/net przy kapitalizacji. Utrzymywany ręcznie w arkuszu; test scenariuszowy EOD go czyta.

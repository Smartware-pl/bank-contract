# Generator kontraktu zdarzeń: asyncapi.yaml + schemas/*.json + examples/*.json (jedno źródło prawdy: ten skrypt).
import io, json, os

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")


def w(rel, content):
    p = os.path.join(ROOT, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    io.open(p, "w", encoding="utf-8", newline="\n").write(content if isinstance(content, str) else json.dumps(content, ensure_ascii=False, indent=2) + "\n")


UUID = {"type": "string", "format": "uuid"}
DATE = {"type": "string", "format": "date"}
DATETIME = {"type": "string", "format": "date-time"}
IBAN = {"type": "string", "minLength": 15, "maxLength": 34, "description": "IBAN bez spacji"}
EMAIL = {"type": "string", "format": "email", "description": "Adres odbiorcy wiadomości — jedyne PII poza identyfikatorami; obecne tylko w zdarzeniach konsumowanych przez notifications"}
MONEY_REF = {"$ref": "../money.json"}

# type -> (topic key, aggregateType, producer, description, properties, required, consumers)
EVENTS = {
    "customer.created": ("customers", "Customer", "core-api", "Utworzono klienta. notifications → mail powitalny.",
        {"customerId": UUID, "email": EMAIL, "fullName": {"type": "string", "description": "Do zwrotu grzecznościowego w mailu"}},
        ["customerId", "email"], ["notifications"]),
    "account.opened": ("accounts", "Account", "core-api", "Otwarto rachunek. notifications → mail z numerem rachunku.",
        {"accountId": UUID, "customerId": UUID, "email": EMAIL, "iban": IBAN, "productCode": {"type": "string"}, "productName": {"type": "string"}},
        ["accountId", "customerId", "iban", "productCode"], ["notifications"]),
    "payment.confirmation_requested": ("payments", "Payment", "core-api",
        "Płatność czeka na kod potwierdzenia. Jedyny payload z sekretem (`code` jawny) — core-api trzyma wyłącznie hash; konsument nie loguje payloadu.",
        {"paymentId": UUID, "customerId": UUID, "email": EMAIL, "code": {"type": "string", "pattern": "^[0-9]{6}$", "description": "Kod potwierdzenia — sekret, nie logować"},
         "expiresAt": DATETIME, "amount": MONEY_REF, "creditorName": {"type": "string"}, "creditorIban": IBAN, "title": {"type": "string"}, "reference": {"type": "string", "description": "PAY-<yyyymmdd>-<6 base32>"}},
        ["paymentId", "customerId", "email", "code", "expiresAt", "amount"], ["notifications"]),
    "payment.posted": ("payments", "Payment", "core-api",
        "Płatność zaksięgowana. notifications → mail; clearing-sim → dla `external=true` i `kind=EXTERNAL_OUT` publikuje po opóźnieniu `clearing.settled` albo `clearing.returned`.",
        {"paymentId": UUID, "kind": {"type": "string", "enum": ["INTERNAL", "EXTERNAL_OUT", "EXTERNAL_IN"]}, "debtorAccountId": UUID, "debtorIban": IBAN,
         "creditorIban": IBAN, "creditorName": {"type": "string"}, "amount": MONEY_REF, "title": {"type": "string"}, "businessDate": DATE,
         "external": {"type": "boolean", "description": "true = odbiorca poza bankiem (idzie do izby)"},
         "customerId": UUID, "email": EMAIL, "reference": {"type": "string"}},
        ["paymentId", "kind", "debtorAccountId", "debtorIban", "creditorIban", "creditorName", "amount", "title", "businessDate", "external"], ["notifications", "clearing-sim"]),
    "payment.rejected": ("payments", "Payment", "core-api", "Płatność odrzucona (walidacja, wygasły kod, brak środków przy zleceniu stałym).",
        {"paymentId": UUID, "reason": {"type": "string", "description": "Slug problemu (`insufficient-funds`, `confirmation-expired`, …)"},
         "customerId": UUID, "email": EMAIL, "amount": MONEY_REF, "creditorName": {"type": "string"}, "title": {"type": "string"}, "reference": {"type": "string"}},
        ["paymentId", "reason"], ["notifications"]),
    "payment.settled": ("payments", "Payment", "core-api", "Izba rozliczyła płatność zewnętrzną (albo wewnętrzna rozliczona natychmiast).",
        {"paymentId": UUID, "clearingRef": {"type": "string"}, "customerId": UUID, "email": EMAIL, "amount": MONEY_REF, "creditorName": {"type": "string"}, "reference": {"type": "string"}},
        ["paymentId"], ["notifications"]),
    "payment.returned": ("payments", "Payment", "core-api", "Zwrot z izby albo ręczny zwrot operatora; zaksięgowano storno.",
        {"paymentId": UUID, "reasonCode": {"type": "string", "enum": ["AC01", "AC04", "AM04", "MS03"]}, "reversalEntryId": UUID,
         "customerId": UUID, "email": EMAIL, "amount": MONEY_REF, "creditorName": {"type": "string"}, "reference": {"type": "string"}},
        ["paymentId", "reasonCode", "reversalEntryId"], ["notifications"]),
    "payment.incoming_credited": ("payments", "Payment", "core-api", "Przelew przychodzący z izby uznał rachunek klienta.",
        {"paymentId": UUID, "creditorAccountId": UUID, "amount": MONEY_REF, "debtorName": {"type": "string"}, "debtorIban": IBAN, "title": {"type": "string"},
         "customerId": UUID, "email": EMAIL, "creditorIban": IBAN, "reference": {"type": "string"}},
        ["paymentId", "creditorAccountId", "amount", "debtorName", "title"], ["notifications"]),
    "payment.incoming_rejected": ("payments", "Payment", "core-api", "Przelew przychodzący odrzucony (nieznany IBAN albo rachunek `CLOSED`); nic nie zaksięgowano. clearing-sim symuluje zwrot do nadawcy.",
        {"clearingRef": {"type": "string"}, "creditorIban": IBAN, "reasonCode": {"type": "string", "enum": ["AC01", "AC04", "MS03"]}, "amount": MONEY_REF},
        ["clearingRef", "creditorIban", "reasonCode"], ["clearing-sim"]),
    "interest.capitalized": ("interest", "Account", "core-api", "Kapitalizacja odsetek na rachunku (gross, podatek, net).",
        {"accountId": UUID, "customerId": UUID, "email": EMAIL, "iban": IBAN, "gross": MONEY_REF, "tax": MONEY_REF, "net": MONEY_REF, "periodStart": DATE, "periodEnd": DATE},
        ["accountId", "customerId", "gross", "tax", "net", "periodStart", "periodEnd"], ["notifications"]),
    "businessday.closed": ("batch", "BusinessDay", "core-api", "Zamknięto dzień biznesowy; następny jest OPEN. Dziś tylko do obserwacji (Console).",
        {"businessDate": DATE, "nextBusinessDate": DATE, "jobRunId": UUID},
        ["businessDate", "nextBusinessDate", "jobRunId"], []),
    "clearing.settled": ("clearing", "Payment", "clearing-sim", "Izba rozliczyła płatność wychodzącą. core-api → `SETTLED`, publikuje `payment.settled`.",
        {"clearingRef": {"type": "string", "description": "CLR-<yyyy>-<6 cyfr>"}, "paymentId": UUID, "settledAt": DATETIME},
        ["clearingRef", "paymentId", "settledAt"], ["core-api"]),
    "clearing.returned": ("clearing", "Payment", "clearing-sim", "Izba zwróciła płatność wychodzącą. core-api → storno, `RETURNED`, publikuje `payment.returned`.",
        {"clearingRef": {"type": "string"}, "paymentId": UUID, "reasonCode": {"type": "string", "enum": ["AC01", "AC04", "AM04", "MS03"]}},
        ["clearingRef", "paymentId", "reasonCode"], ["core-api"]),
    "clearing.incoming_received": ("clearing", "IncomingTransfer", "clearing-sim", "Przelew przychodzący z izby. core-api → `TRANSFER_IN` + `payment.incoming_credited` albo `payment.incoming_rejected`.",
        {"clearingRef": {"type": "string"}, "debtorIban": IBAN, "debtorName": {"type": "string"}, "creditorIban": IBAN, "amount": MONEY_REF, "title": {"type": "string"}, "valueDate": DATE},
        ["clearingRef", "debtorIban", "debtorName", "creditorIban", "amount", "title", "valueDate"], ["core-api"]),
}

TOPICS = {
    "customers": ("bank.customers.v1", "core-api", ["notifications"]),
    "accounts": ("bank.accounts.v1", "core-api", ["notifications"]),
    "payments": ("bank.payments.v1", "core-api", ["notifications", "clearing-sim"]),
    "interest": ("bank.interest.v1", "core-api", ["notifications"]),
    "batch": ("bank.batch.v1", "core-api", []),
    "clearing": ("bank.clearing.v1", "clearing-sim", ["core-api"]),
}

def camel(t):
    parts = t.replace(".", "_").split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])

def pascal(t):
    return "".join(p.capitalize() for p in t.replace(".", "_").split("_"))

# ── money.json, envelope.json ─────────────────────────────────────────────
w("schemas/money.json", {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://bank.local/schemas/money.json",
    "title": "Money",
    "description": "Kwota w jednostkach mniejszych (grosze) + kod ISO 4217. Nigdy liczby zmiennoprzecinkowe.",
    "type": "object",
    "additionalProperties": False,
    "required": ["minor", "currency"],
    "properties": {
        "minor": {"type": "integer", "existingJavaType": "java.lang.Long", "description": "Grosze; znak wg kontekstu pola"},
        "currency": {"type": "string", "pattern": "^[A-Z]{3}$"},
    },
})

w("schemas/envelope.json", {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://bank.local/schemas/envelope.json",
    "title": "EventEnvelope",
    "description": "Wspólna koperta wszystkich zdarzeń (docs/integration-contracts.md §4). Konsument deduplikuje po `id`; klucz partycji = `aggregateId`.",
    "type": "object",
    "required": ["id", "type", "version", "occurredAt", "businessDate", "producer", "aggregateType", "aggregateId", "correlationId", "payload"],
    "properties": {
        "id": {"type": "string", "format": "uuid", "description": "UUID v7 — do deduplikacji w inboxie"},
        "type": {"type": "string", "pattern": "^[a-z]+\\.[a-z_]+$", "description": "Nazwa zdarzenia w czasie przeszłym, np. payment.posted"},
        "version": {"type": "integer", "minimum": 1, "description": "Wersja zdarzenia; zmiana niekompatybilna = +1"},
        "occurredAt": {"type": "string", "format": "date-time", "description": "RFC 3339 UTC"},
        "businessDate": {"type": "string", "format": "date"},
        "producer": {"type": "string", "enum": ["core-api", "clearing-sim"]},
        "aggregateType": {"type": "string"},
        "aggregateId": {"type": "string", "description": "Klucz partycji; kolejność gwarantowana tylko w jego obrębie"},
        "correlationId": {"type": "string", "format": "uuid"},
        "causationId": {"type": ["string", "null"], "format": "uuid", "description": "id zdarzenia, które wywołało to zdarzenie"},
        "payload": {"type": "object", "existingJavaType": "com.fasterxml.jackson.databind.JsonNode", "description": "Schemat zależy od `type` — schemas/payloads/<type>.json"},
    },
})

w("schemas/kafka-headers.json", {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://bank.local/schemas/kafka-headers.json",
    "title": "KafkaHeaders",
    "description": "Nagłówki Kafka duplikujące pola koperty — do filtrowania bez deserializacji.",
    "type": "object",
    "required": ["type", "version", "correlationId"],
    "properties": {"type": {"type": "string"}, "version": {"type": "string", "description": "Liczba jako tekst"}, "correlationId": {"type": "string", "format": "uuid"}},
})

# ── payloads + events + examples ────────────────────────────────────────
EXAMPLE_IDS = {
    "customerId": "0191f7a0-0001-7000-8000-000000000001",
    "accountId": "0191f7a0-1111-7000-8000-000000000001",
    "creditorAccountId": "0191f7a0-1111-7000-8000-000000000002",
    "debtorAccountId": "0191f7a0-1111-7000-8000-000000000001",
    "paymentId": "0191f7a0-5b1d-7c3e-8a00-abcdefabcdef",
    "reversalEntryId": "0191f7a0-2222-7000-8000-000000000009",
    "jobRunId": "0191f7a0-3333-7000-8000-000000000001",
}
EXAMPLE_VALUES = {
    "email": "jan.kowalski@example.com", "fullName": "Jan Kowalski", "iban": "PL61100000000000000000000001",
    "debtorIban": "PL61100000000000000000000001", "creditorIban": "PL27114020040000300201355387",
    "creditorName": "Anna Nowak", "debtorName": "Firma Alfa sp. z o.o.", "productCode": "SAVINGS_STD", "productName": "Konto oszczędnościowe",
    "code": "482913", "expiresAt": "2026-09-08T10:30:30Z", "title": "Faktura 12/2026", "reference": "PAY-20260908-7K3M2Q",
    "kind": "EXTERNAL_OUT", "businessDate": "2026-09-08", "external": True, "reason": "insufficient-funds",
    "clearingRef": "CLR-2026-000123", "reasonCode": "AC01", "periodStart": "2026-09-01", "periodEnd": "2026-09-30",
    "nextBusinessDate": "2026-09-09", "settledAt": "2026-09-08T10:15:45Z", "valueDate": "2026-09-08",
}
MONEY_EXAMPLES = {"amount": 12345, "gross": 4110, "tax": 781, "net": 3329}

asyncapi_messages = {}
for t, (topic_key, aggregate, producer, desc, props, required, consumers) in EVENTS.items():
    payload_schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"https://bank.local/schemas/payloads/{t}.json",
        "title": f"{pascal(t)}Payload",
        "description": desc,
        "type": "object",
        "additionalProperties": True,
        "required": required,
        "properties": props,
    }
    w(f"schemas/payloads/{t}.json", payload_schema)
    event_schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"https://bank.local/schemas/events/{t}.json",
        "title": f"{pascal(t)}Event",
        "description": f"Koperta zdarzenia `{t}` (version 1).",
        "allOf": [
            {"$ref": "../envelope.json"},
            {"type": "object", "properties": {
                "type": {"const": t},
                "version": {"const": 1},
                "producer": {"const": producer},
                "aggregateType": {"const": aggregate},
                "payload": {"$ref": f"../payloads/{t}.json"},
            }},
        ],
    }
    w(f"schemas/events/{t}.json", event_schema)

    payload = {}
    for name in props:
        if name in MONEY_EXAMPLES:
            payload[name] = {"minor": MONEY_EXAMPLES[name], "currency": "PLN"}
        elif name in EXAMPLE_IDS:
            payload[name] = EXAMPLE_IDS[name]
        elif name in EXAMPLE_VALUES:
            payload[name] = EXAMPLE_VALUES[name]
        else:
            raise SystemExit(f"no example for {t}.{name}")
    if t == "payment.incoming_rejected":
        payload["creditorIban"] = "PL61100000000000000000000099"
    if t == "payment.returned":
        payload["reasonCode"] = "MS03"
    agg_id = payload.get("paymentId") or payload.get("accountId") or payload.get("customerId") or payload.get("clearingRef") or payload.get("businessDate")
    example = {
        "id": "0191f7a0-6c3e-7b2a-9f00-1234567890ab",
        "type": t,
        "version": 1,
        "occurredAt": "2026-09-08T10:15:30Z",
        "businessDate": "2026-09-08",
        "producer": producer,
        "aggregateType": aggregate,
        "aggregateId": agg_id,
        "correlationId": "0191f7a0-4a0c-7d4f-9b00-fedcbafedcba",
        "causationId": "0191f7a0-6c3e-7b2a-9f00-000000000001" if t.startswith(("payment.settled", "payment.returned", "payment.incoming")) else None,
        "payload": payload,
    }
    w(f"examples/{t}.json", example)

    asyncapi_messages[camel(t)] = {
        "name": t,
        "title": t,
        "summary": desc.split(".")[0] + ".",
        "description": desc + (f" Konsumenci: {', '.join(consumers)}." if consumers else " Bez konsumentów (obserwacja w Redpanda Console)."),
        "contentType": "application/json",
        "headers": {"$ref": "./schemas/kafka-headers.json"},
        "payload": {"$ref": f"./schemas/events/{t}.json"},
        "examples": [{"name": "przykład", "payload": {"$ref": f"./examples/{t}.json"}}],
    }

# ── asyncapi.yaml ────────────────────────────────────────────────────────
def yaml_dump(obj, indent=0):
    """Minimalny, deterministyczny dumper YAML (klucze w kolejności wstawienia, stringi cytowane gdzie trzeba)."""
    pad = "  " * indent
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            key = k if k.replace("-", "").replace("_", "").replace(".", "").isalnum() and not k[0].isdigit() else json.dumps(k)
            if isinstance(v, (dict, list)) and v:
                out.append(f"{pad}{key}:")
                out.append(yaml_dump(v, indent + 1))
            else:
                out.append(f"{pad}{key}: {scalar(v)}")
    elif isinstance(obj, list):
        for v in obj:
            if isinstance(v, (dict, list)):
                inner = yaml_dump(v, indent + 1).splitlines()
                out.append(f"{pad}- " + inner[0].strip())
                out.extend(inner[1:])
            else:
                out.append(f"{pad}- {scalar(v)}")
    return "\n".join(out)

def scalar(v):
    if v is None: return "null"
    if isinstance(v, bool): return "true" if v else "false"
    if isinstance(v, (int, float)): return str(v)
    if isinstance(v, (dict, list)) and not v: return "{}" if isinstance(v, dict) else "[]"
    return json.dumps(v, ensure_ascii=False)

channels = {}
operations = {}
for key, (address, producer, consumers) in TOPICS.items():
    msgs = {camel(t): {"$ref": f"#/components/messages/{camel(t)}"} for t, ev in EVENTS.items() if ev[0] == key}
    channels[key] = {
        "address": address,
        "description": f"Temat `{address}`. Producent: {producer}. Konsumenci: {', '.join(consumers) if consumers else 'brak (obserwacja)'}. Klucz wiadomości = aggregateId. Retencja dev 7 dni. DLQ: `{address}.dlq`.",
        "messages": msgs,
        "bindings": {"kafka": {"topic": address, "partitions": 1, "topicConfiguration": {"retention.ms": 604800000, "cleanup.policy": ["delete"]}, "bindingVersion": "0.5.0"}},
    }
    operations[f"{camel(producer)}Publishes{key.capitalize()}"] = {
        "action": "send",
        "channel": {"$ref": f"#/channels/{key}"},
        "summary": f"{producer} publikuje na {address}" + (" (przez transactional outbox + relay)" if producer == "core-api" else " (bezpośrednio, acks=all)"),
        "messages": [{"$ref": f"#/channels/{key}/messages/{m}"} for m in msgs],
        "bindings": {"kafka": {"bindingVersion": "0.5.0"}},
    }
    for c in consumers:
        group = {"notifications": "notifications", "clearing-sim": "clearing-sim", "core-api": "core-api-payments"}[c]
        consumed = [m for m in msgs if c in EVENTS[[t for t in EVENTS if camel(t) == m][0]][6]]
        operations[f"{camel(c)}Consumes{key.capitalize()}"] = {
            "action": "receive",
            "channel": {"$ref": f"#/channels/{key}"},
            "summary": f"{c} konsumuje {address} (grupa `{group}`, inbox po `id`, nieznane `type` ignoruje, błąd → retry 3× → DLQ)",
            "messages": [{"$ref": f"#/channels/{key}/messages/{m}"} for m in consumed],
            "bindings": {"kafka": {"groupId": {"type": "string", "enum": [group]}, "bindingVersion": "0.5.0"}},
        }

doc = {
    "asyncapi": "3.0.0",
    "id": "urn:bank:event-bus",
    "info": {
        "title": "bank event bus",
        "version": "0.3.0",
        "description": (
            "Normatywny opis szyny zdarzeń (Redpanda, Kafka API) — docs/integration-contracts.md §4–5. "
            "Jedna koperta dla wszystkich zdarzeń (schemas/envelope.json), schemat payloadu per `type` (schemas/payloads/), "
            "pełny schemat zdarzenia (schemas/events/) używany w testach kontraktowych obu stron. "
            "Przez szynę idą wyłącznie fakty w czasie przeszłym; żadnych komend ani request-reply. "
            "Zmiany kompatybilne = nowe opcjonalne pole albo nowy `type`; niekompatybilne = `version`+1. "
            "Historia: v0.3 (2026-09-10) pierwsza wersja — 14 zdarzeń, 6 tematów; pola `email`/`customerId`/`amount` w `payment.*` i `interest.capitalized` dla notifications."
        ),
        "contact": {"name": "bank-contract (CODEOWNERS)"},
    },
    "defaultContentType": "application/json",
    "servers": {
        "redpanda-dev": {"host": "redpanda:9092", "protocol": "kafka", "description": "Broker w docker-compose bank-infra (z hosta localhost:19092). Tematy tworzy bank-infra (`make topics`), nie aplikacje."},
    },
    "channels": channels,
    "operations": operations,
    "components": {
        "messages": asyncapi_messages,
        "schemas": {
            "EventEnvelope": {"$ref": "./schemas/envelope.json"},
            "Money": {"$ref": "./schemas/money.json"},
            "KafkaHeaders": {"$ref": "./schemas/kafka-headers.json"},
        },
    },
}
w("asyncapi.yaml", "# Generowane ze skryptu w PR (asyncapi/README.md); edytuj świadomie — schematy w schemas/ są normatywne.\n" + yaml_dump(doc) + "\n")
print("events:", len(EVENTS), "topics:", len(TOPICS), "operations:", len(operations))

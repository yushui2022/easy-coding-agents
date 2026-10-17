"""Durable per-attempt provider usage and Decimal price snapshots."""
from decimal import Decimal, InvalidOperation
import json
import time

RATES = {"input", "output", "cache_read", "cache_write", "cache_write_5m", "cache_write_1h"}


def validate_pricing(pricing):
    if not isinstance(pricing, dict):
        raise ValueError("pricing must be a table keyed by model")
    for model, rates in pricing.items():
        if not isinstance(model, str) or not isinstance(rates, dict) or set(rates) - (RATES | {"currency"}):
            raise ValueError("Invalid pricing entry")
        if not isinstance(rates.get("currency"), str) or not rates["currency"].strip():
            raise ValueError("Pricing requires a currency")
        for key, value in rates.items():
            if key == "currency":
                continue
            try:
                number = Decimal(str(value))
                if not number.is_finite() or number < 0:
                    raise ValueError("Prices must be finite and nonnegative")
            except InvalidOperation:
                raise ValueError("Prices must be decimal amounts per million tokens") from None


def normalize(raw, protocol):
    def count(key, default=None, source=None):
        value = (raw if source is None else source).get(key, default)
        if type(value) is not int or value < 0:
            raise ValueError("Unknown token count")
        return value
    try:
        if protocol == "anthropic":
            tokens = dict(input=count("input_tokens"), output=count("output_tokens"),
                          cache_read=count("cache_read_input_tokens", 0))
            creation = count("cache_creation_input_tokens", 0)
            details = raw.get("cache_creation")
            if details and creation:
                tokens["cache_write_5m"] = count("ephemeral_5m_input_tokens", 0, details)
                tokens["cache_write_1h"] = count("ephemeral_1h_input_tokens", 0, details)
                if tokens["cache_write_5m"] + tokens["cache_write_1h"] != creation:
                    return None
            else:
                tokens["cache_write"] = creation
        else:
            prompt, output = count("prompt_tokens"), count("completion_tokens")
            details = raw.get("prompt_tokens_details") or {}
            cached = count("prompt_cache_hit_tokens", details.get("cached_tokens", 0) or 0)
            if cached > prompt:
                return None
            tokens = dict(input=prompt-cached, cache_read=cached, output=output)
        return tokens
    except (ValueError, TypeError, AttributeError):
        return None


def calculate(tokens, rates):
    if tokens is None or not rates:
        return None
    if any(value and key not in rates for key, value in tokens.items()):
        return None
    return str(sum((Decimal(value) * Decimal(str(rates.get(key, 0))) / Decimal(1_000_000)
                    for key, value in tokens.items()), Decimal(0)))


class UsageLedger:
    def __init__(self, store):
        self.db = store.db
        self.db.execute("""CREATE TABLE IF NOT EXISTS usage_requests (
            id TEXT PRIMARY KEY, session_id TEXT, root_id TEXT, model TEXT, protocol TEXT,
            purpose TEXT, status TEXT, created REAL, rates TEXT, usage TEXT, tokens TEXT, cost TEXT)""")
        self.db.commit()

    def begin(self, ident, state, settings, purpose):
        with self.db:
            self.db.execute("INSERT INTO usage_requests VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (ident, state['id'], state.get('billing_root', state['id']), settings.model,
                 settings.api_format, purpose, 'pending', time.time(),
                 json.dumps(settings.pricing.get(settings.model, {})), '{}', 'null', None))

    def finish(self, ident, usage, status):
        row = self.db.execute("SELECT protocol,rates FROM usage_requests WHERE id=?", (ident,)).fetchone()
        if not row:
            return
        tokens = normalize(usage, row[0])
        rates = json.loads(row[1])
        cost = calculate(tokens, rates)
        # Some compatible providers omit the cache split. Different cache rates
        # cannot be applied exactly when that count is absent.
        details = usage.get('prompt_tokens_details') or {}
        if (row[0] == 'openai' and 'prompt_cache_hit_tokens' not in usage
                and details.get('cached_tokens') is None and 'cache_read' in rates
                and rates.get('cache_read') != rates.get('input')):
            cost = None
        with self.db:
            self.db.execute("UPDATE usage_requests SET status=?,usage=?,tokens=?,cost=? WHERE id=?",
                            (status, json.dumps(usage), json.dumps(tokens), cost, ident))

    def summary(self, state):
        rows = self.db.execute("SELECT status,rates,tokens,cost,purpose,session_id FROM usage_requests WHERE root_id=?",
                               (state.get('billing_root', state['id']),)).fetchall()
        totals, costs, unknown_usage, unknown_cost = {}, {}, 0, 0
        for status, rates, tokens, cost, _, _ in rows:
            parsed = json.loads(tokens)
            if parsed is None or status != 'complete':
                unknown_usage += 1
            if parsed:
                for key, value in parsed.items():
                    totals[key] = totals.get(key, 0) + value
            if cost is None or status != 'complete':
                unknown_cost += 1
            if cost is not None:
                currency = json.loads(rates)['currency']
                costs[currency] = costs.get(currency, Decimal(0)) + Decimal(cost)
        return dict(scope='root session and all descendants', requests=len(rows),
                    reported_tokens=totals, priced_subtotals={k:str(v) for k,v in costs.items()},
                    incomplete_usage_requests=unknown_usage, incomplete_cost_requests=unknown_cost,
                    historical_usage_untracked=not state.get('usage_tracking_complete', False),
                    billing_note='Calculated from provider usage and configured price snapshots; not an invoice.')

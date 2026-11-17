-- Append-only ledger. Rows are inserted, never rewritten, except for the
-- mutable status columns on markets and orders. Times are Unix seconds (UTC).

CREATE TABLE IF NOT EXISTS series (
    ticker          TEXT PRIMARY KEY,
    title           TEXT,
    category        TEXT,
    frequency       TEXT,
    fee_type        TEXT,
    fee_multiplier  REAL,
    tags            TEXT,
    updated_ts      INTEGER
);

CREATE TABLE IF NOT EXISTS events (
    event_ticker        TEXT PRIMARY KEY,
    series_ticker       TEXT,
    title               TEXT,
    sub_title           TEXT,
    mutually_exclusive  INTEGER,
    first_seen_ts       INTEGER
);

CREATE TABLE IF NOT EXISTS markets (
    ticker                  TEXT PRIMARY KEY,
    event_ticker            TEXT,
    series_ticker           TEXT,
    title                   TEXT,
    yes_sub_title           TEXT,
    rules_primary           TEXT,
    rules_secondary         TEXT,
    open_ts                 INTEGER,
    close_ts                INTEGER,
    expected_expiration_ts  INTEGER,
    can_close_early         INTEGER,
    status                  TEXT,
    result                  TEXT,
    settlement_ts           INTEGER,
    first_seen_ts           INTEGER,
    updated_ts              INTEGER
);
CREATE INDEX IF NOT EXISTS markets_event ON markets(event_ticker);
CREATE INDEX IF NOT EXISTS markets_status ON markets(status);

CREATE TABLE IF NOT EXISTS snapshots (
    ticker         TEXT NOT NULL,
    ts             INTEGER NOT NULL,
    yes_bid        REAL,
    yes_ask        REAL,
    yes_bid_size   REAL,
    yes_ask_size   REAL,
    last_price     REAL,
    volume         REAL,
    volume_24h     REAL,
    open_interest  REAL,
    PRIMARY KEY (ticker, ts)
) WITHOUT ROWID;

-- Rules text exactly as it read when we decided, so a later edit is visible.
CREATE TABLE IF NOT EXISTS rules_text (
    hash   TEXT PRIMARY KEY,
    ticker TEXT,
    ts     INTEGER,
    text   TEXT
);

-- One run of the forecasting pipeline over one event.
CREATE TABLE IF NOT EXISTS forecast_runs (
    id                TEXT PRIMARY KEY,
    event_ticker      TEXT,
    created_ts        INTEGER,
    pipeline_version  TEXT,
    holdout           INTEGER,   -- 1 = picked at random and not screened
    tradable          INTEGER,   -- 0 = shadow-only category
    screen            TEXT,
    dossier           TEXT,
    skipped           TEXT,      -- why the run produced no forecast, if it did not
    cost_usd          REAL,
    duration_s        REAL
);
CREATE INDEX IF NOT EXISTS forecast_runs_event ON forecast_runs(event_ticker, created_ts);

-- One row per model sample per market.
CREATE TABLE IF NOT EXISTS forecasts (
    id          TEXT PRIMARY KEY,
    run_id      TEXT,
    ticker      TEXT,
    model       TEXT,
    sample_idx  INTEGER,
    p           REAL,
    rationale   TEXT,
    cost_usd    REAL
);
CREATE INDEX IF NOT EXISTS forecasts_run ON forecasts(run_id);

-- One row per trade/no-trade decision, including every reason code.
CREATE TABLE IF NOT EXISTS decisions (
    id                TEXT PRIMARY KEY,
    run_id            TEXT,
    kind              TEXT,     -- 'forecast' = made when the forecast was; 'requote' / 'exit' = later
    ticker            TEXT,
    event_ticker      TEXT,
    cluster           TEXT,
    created_ts        INTEGER,
    mode              TEXT,
    strategy          TEXT,
    pipeline_version  TEXT,
    holdout           INTEGER,
    tradable          INTEGER,
    yes_bid           REAL,
    yes_ask           REAL,
    mid               REAL,
    p_model           REAL,     -- model probability before blending
    p_spread          REAL,     -- standard deviation across the ensemble
    p_final           REAL,     -- after calibration and market blend
    w_market          REAL,
    side              TEXT,     -- 'yes' / 'no' / NULL
    limit_price       REAL,     -- price paid for the side bought
    fee               REAL,
    edge              REAL,
    kelly             REAL,
    contracts         INTEGER,
    action            TEXT,     -- 'order' / 'skip'
    reasons           TEXT
);
CREATE INDEX IF NOT EXISTS decisions_ticker ON decisions(ticker);

CREATE TABLE IF NOT EXISTS orders (
    client_order_id    TEXT PRIMARY KEY,
    decision_id        TEXT,
    ticker             TEXT,
    side               TEXT,     -- 'yes' / 'no' (the side bought)
    price              REAL,
    contracts          INTEGER,
    mode               TEXT,
    status             TEXT,     -- resting / filled / partial / cancelled / expired / rejected
    exchange_order_id  TEXT,
    created_ts         INTEGER,
    expires_ts         INTEGER,
    updated_ts         INTEGER
);

CREATE TABLE IF NOT EXISTS fills (
    id               TEXT PRIMARY KEY,
    client_order_id  TEXT,
    ticker           TEXT,
    side             TEXT,
    price            REAL,
    contracts        REAL,
    fee              REAL,
    ts               INTEGER,
    simulated        INTEGER
);
CREATE INDEX IF NOT EXISTS fills_ticker ON fills(ticker);

-- Estimated liquidity-reward earnings, one row per resting order per cycle.
-- An estimate from order-book snapshots; in live mode Kalshi's credits are the truth.
CREATE TABLE IF NOT EXISTS lp_accruals (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    ts               INTEGER,
    mode             TEXT,
    ticker           TEXT,
    side             TEXT,
    client_order_id  TEXT,
    seconds          REAL,
    share            REAL,     -- of that side's score
    usd              REAL
);
CREATE INDEX IF NOT EXISTS lp_accruals_ticker ON lp_accruals(ticker);

CREATE TABLE IF NOT EXISTS risk_events (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts      INTEGER,
    kind    TEXT,
    detail  TEXT
);

CREATE TABLE IF NOT EXISTS kv (
    key    TEXT PRIMARY KEY,
    value  TEXT
);

# PayPal Conditional Autopay — AI Mandate Firewall (Production Edition)

> **Zero-Demo, Production-Grade FinTech System**  
> Built with Python Flask, Persistent Relational SQLite (`autopay.db`), and official **PayPal REST API v2/v3** endpoints (`/v1/oauth2/token`, `/v3/vault/setup-tokens`, `/v2/checkout/orders`).

---

## 1. Production Architecture & Core Differentiator

Traditional Autopay is **"blind"**: it automatically debits funds on fixed calendar dates regardless of price spikes, unexpected surcharges, or delayed incoming cashflow.

**PayPal Conditional Autopay** acts as an **AI Mandate Firewall**:
Users write rules in plain English. When an external trigger (PayPal webhook, vendor invoice, or external milestone) hits the system, the AI Agent evaluates conditions **BEFORE money moves**:
- **Condition Met ($\text{TRUE}$)**: Executes instant capture via PayPal Orders v2 & Payment Method Vaulting.
- **Condition Violated ($\text{FALSE}$)**: **Freezes the transaction before a single dollar leaves the wallet**, increments the **"Protected by AI Firewall"** metric, and triggers a Human-in-the-Loop review card with one-click **Approve & Pay via PayPal** or **Reject & Dispute**.

```
[1. Webhook / Bill Ingested] ---> [2. AI Mandate Firewall] ---> [3. PayPal Vault Token] ---> [4. Orders v2 Capture / Freeze]
```

---

## 2. Relational SQLite Schema (`autopay.db`)

Zero pre-seeded fake data. Initializes completely fresh with 4 production tables:

1. **`paypal_account`**:
   - `id`: Singleton ID (`1`)
   - `client_id`, `client_secret`: PayPal Developer REST API credentials
   - `environment`: `'sandbox'` (`api-m.sandbox.paypal.com`) or `'live'` (`api-m.paypal.com`)
   - `merchant_email`: Merchant identification email
   - `vault_setup_token`: PayPal Vault Setup Token (`v3/vault/setup-tokens`)
   - `connected_status`: `'CONNECTED'`, `'DISCONNECTED'`, or `'ERROR'`
   - `total_saved_by_ai`: Running dollar amount protected from fraudulent/spiked charges
   - `total_auto_settled`: Running dollar amount automatically captured

2. **`rules`** (Active Conditional Mandates):
   - `id`: Auto-incrementing Primary Key
   - `title`: Short mandate title
   - `natural_language_rule`: Plain English condition typed by user
   - `rule_category`: `'CHAIN_REACTION'`, `'SPLIT_PAYMENT'`, `'BILL_CAP'`, `'MILESTONE'`, `'PRICE_DROP'`
   - `trigger_source`: Event source (e.g., `'Employer Paycheck'`, `'SpeedNet Wi-Fi'`)
   - `recipient_paypal_email`: Payee PayPal email address
   - `recipient_name`: Payee name
   - `payment_amount`: Target payout amount
   - `currency`: Default `'USD'`
   - `condition_operator`: `'>='`, `'<='`, `'=='`
   - `condition_threshold`: Condition bound
   - `vault_token_id`: Unique PayPal vault mandate token
   - `status`: `'ACTIVE_WAITING'`, `'EXECUTED'`, `'BLOCKED_BY_AI'`, `'OVERRIDDEN'`, `'REJECTED'`, `'PAUSED'`
   - `pending_invoice_amount`: Stored spiked amount awaiting human-in-the-loop review
   - `pending_event_payload`: Stored incoming event payload

3. **`audit_logs`** (Immutable Security & PayPal API Ledger):
   - `id`: Auto-incrementing Primary Key
   - `timestamp`: ISO timestamp
   - `rule_id`: Associated rule ID
   - `event_source`: Source of the ingested event
   - `event_title`: Summary title
   - `raw_webhook_json`: Formatted incoming webhook JSON payload
   - `ai_reasoning_steps`: JSON array of step-by-step firewall checks (`[✓]`, `[✗]`, `[!]`)
   - `paypal_api_trace`: Real or dry-run PayPal Orders v2 request & response JSON including PayPal Order ID
   - `verdict`: `'CAPTURED'`, `'BLOCKED'`, `'CHAIN_TRIGGERED'`, `'HOLD_INSUFFICIENT_TRIGGER'`, `'USER_OVERRIDE'`, `'DISPUTED'`
   - `amount_impact`: Dollar impact

4. **`system_config`**:
   - `key`, `value`: Stores `gemini_api_key`, `webhook_secret_key`, and system settings.

---

## 3. Real PayPal REST API v2/v3 Integration

- **OAuth2 Token Authentication**: `POST /v1/oauth2/token`
  - Performs live handshake using HTTP Basic Auth (`client_id`, `client_secret`).
- **Payment Method Vaulting**: `POST /v3/vault/setup-tokens`
  - Authorizes future conditional payments without re-prompting the customer.
- **Orders v2 Creation & Capture**:
  - `POST /v2/checkout/orders` with `intent: "CAPTURE"`, `purchase_units`, and vaulted payment source.
  - `POST /v2/checkout/orders/{id}/capture` to execute instant settlement when approved.
- **Webhook Signature Validation**: `POST /v1/notifications/verify-webhook-signature`

---

## 4. Webhook Ingestion Endpoints

### 1. PayPal Webhooks: `POST /api/webhooks/paypal`
Receives events from the PayPal Developer Portal (`PAYMENT.CAPTURE.COMPLETED`, `INVOICING.INVOICE.PAID`). Automatically evaluates downstream chain-reaction payouts and team splits.

### 2. External Bill / Milestone Webhooks: `POST /api/webhooks/external`
Receives vendor invoices, GitHub PR merges, or price tracker alerts.
```bash
curl -X POST http://localhost:5000/api/webhooks/external \
  -H "Content-Type: application/json" \
  -d '{
    "trigger_source": "SpeedNet Wi-Fi",
    "amount": 85.00,
    "event_type": "INVOICE_BILLING"
  }'
```

---

## 5. Quickstart & Verification

```bash
# 1. Run production test suite
python test_app.py

# 2. Launch production Flask server
python app.py
```
Open **[http://localhost:5000](http://localhost:5000)** in your browser.

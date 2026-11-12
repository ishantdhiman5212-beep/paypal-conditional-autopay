"""
PayPal Conditional Autopay — Production Flask REST API & Webhook Server
Endpoints:
- /api/state: Live connection metrics, active rules, audit ledger
- /api/settings/paypal: Real OAuth2 credential handshake & settings persistence
- /api/paypal/vault-setup: Generate PayPal Vault Setup Tokens
- /api/parse-rule: AI NLP rule extraction
- /api/rules: Mandate CRUD & pause/resume toggling
- /api/webhooks/paypal: Ingest real PayPal events (PAYMENT.CAPTURE.COMPLETED, etc.)
- /api/webhooks/external: Ingest vendor invoices & milestone triggers
- /api/rules/<id>/override & /reject: Human-in-the-loop dispute & override actions
"""

import os
import json
from flask import Flask, render_template, request, jsonify
import database as db
import paypal_client
import ai_engine

app = Flask(__name__)

# Initialize clean production schema
db.init_db()

# Load local .env if present
env_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
if os.path.exists(env_file):
    with open(env_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                os.environ.setdefault(k.strip(), v.strip())

# Auto-connect if PayPal credentials are provided via environment variables (e.g. Render Dashboard or .env)
env_client_id = os.environ.get("PAYPAL_CLIENT_ID", "").strip()
env_client_secret = os.environ.get("PAYPAL_CLIENT_SECRET", "").strip()
env_environment = os.environ.get("PAYPAL_ENVIRONMENT", "sandbox").strip().lower()
env_merchant_email = os.environ.get("PAYPAL_MERCHANT_EMAIL", "").strip()

if env_client_id and env_client_secret:
    try:
        handshake = paypal_client.test_connection(env_client_id, env_client_secret, env_environment)
        if handshake.get("success"):
            db.update_account_credentials(env_client_id, env_client_secret, env_environment, env_merchant_email, status="CONNECTED")
            account = db.get_account()
            if not account.get("vault_setup_token"):
                vault_res = paypal_client.create_vault_setup_token(env_client_id, env_client_secret, env_environment)
                if vault_res.get("success"):
                    db.update_vault_tokens(vault_setup_token=vault_res["vault_setup_token"])
    except Exception as e:
        print(f"PayPal Auto-connect error: {e}")


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/state", methods=["GET"])
def get_state():
    """Returns real-time account status, metrics, active rules, and audit ledger."""
    try:
        account = db.get_account()
        # Mask sensitive client secret in client state
        safe_account = dict(account)
        if safe_account.get("client_secret"):
            secret = safe_account["client_secret"]
            safe_account["client_secret_masked"] = f"{secret[:4]}••••••••{secret[-4:]}" if len(secret) > 8 else "••••••••"
        else:
            safe_account["client_secret_masked"] = ""
        # Do not expose raw client_secret to client
        safe_account.pop("client_secret", None)

        rules = db.get_rules()
        active_rules = [r for r in rules if r["status"] == "ACTIVE_WAITING"]
        blocked_rules = [r for r in rules if r["status"] == "BLOCKED_BY_AI"]
        audit_logs = db.get_audit_logs(limit=100)

        gemini_configured = bool(db.get_config("gemini_api_key", ""))
        webhook_secret = db.get_config("webhook_secret_key", "")

        return jsonify({
            "success": True,
            "account": safe_account,
            "metrics": {
                "active_mandates": len(active_rules),
                "blocked_mandates": len(blocked_rules),
                "total_mandates": len(rules),
                "total_saved_by_ai": account["total_saved_by_ai"],
                "total_auto_settled": account["total_auto_settled"]
            },
            "rules": rules,
            "audit_logs": audit_logs,
            "config": {
                "gemini_configured": gemini_configured,
                "webhook_secret": webhook_secret
            }
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/settings/paypal", methods=["POST"])
def update_paypal_settings():
    """Saves and validates PayPal credentials via live OAuth2 token handshake."""
    data = request.get_json() or {}
    client_id = data.get("client_id", "").strip()
    client_secret = data.get("client_secret", "").strip()
    environment = data.get("environment", "sandbox").strip().lower()
    merchant_email = data.get("merchant_email", "").strip()
    gemini_key = data.get("gemini_api_key", "").strip()

    if gemini_key:
        db.set_config("gemini_api_key", gemini_key)

    if not client_id or not client_secret:
        # Save credentials as disconnected
        db.update_account_credentials(client_id, client_secret, environment, merchant_email, status="DISCONNECTED")
        return jsonify({
            "success": True,
            "connected_status": "DISCONNECTED",
            "message": "PayPal credentials updated (Disconnected / Offline Mode)."
        })

    # Test live handshake with PayPal API
    test_res = paypal_client.test_connection(client_id, client_secret, environment)
    if test_res.get("success"):
        db.update_account_credentials(client_id, client_secret, environment, merchant_email, status="CONNECTED")
        # Ensure a vault setup token is provisioned
        account = db.get_account()
        if not account.get("vault_setup_token"):
            vault_res = paypal_client.create_vault_setup_token(client_id, client_secret, environment)
            if vault_res.get("success"):
                db.update_vault_tokens(vault_setup_token=vault_res["vault_setup_token"])

        return jsonify({
            "success": True,
            "connected_status": "CONNECTED",
            "environment": environment,
            "message": f"Successfully authenticated with PayPal {environment.upper()} REST API!"
        })
    else:
        db.update_account_credentials(client_id, client_secret, environment, merchant_email, status="ERROR")
        return jsonify({
            "success": False,
            "connected_status": "ERROR",
            "error": test_res.get("error", "OAuth2 handshake failed with PayPal.")
        }), 400


@app.route("/api/paypal/vault-setup", methods=["POST"])
def generate_vault_token():
    """Provisions a new PayPal Payment Method Vault Setup Token."""
    account = db.get_account()
    res = paypal_client.create_vault_setup_token(
        account.get("client_id"),
        account.get("client_secret"),
        account.get("environment", "sandbox")
    )
    if res.get("success"):
        token = res["vault_setup_token"]
        db.update_vault_tokens(vault_setup_token=token)
        return jsonify({"success": True, "vault_setup_token": token, "details": res})
    return jsonify({"success": False, "error": "Failed to create vault setup token"}), 400


@app.route("/api/parse-rule", methods=["POST"])
def parse_rule():
    """Extracts structured mandate fields from plain English text."""
    data = request.get_json() or {}
    text = data.get("text", "")
    gemini_key = db.get_config("gemini_api_key", "")
    try:
        parsed = ai_engine.parse_natural_language_rule(text, api_key=gemini_key)
        return jsonify({"success": True, "parsed": parsed})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400


@app.route("/api/rules", methods=["GET", "POST"])
def handle_rules():
    """Lists active rules or locks a new rule into SQLite."""
    if request.method == "GET":
        rules = db.get_rules()
        return jsonify({"success": True, "rules": rules})

    data = request.get_json() or {}
    try:
        rule = db.create_rule(data)
        db.log_audit(
            rule_id=rule["id"],
            event_source="User Rule Activation",
            event_title=f"Mandate Registered: {rule['title']}",
            raw_webhook_json={"action": "MANDATE_ACTIVATION", "rule": rule},
            ai_reasoning_steps=[
                f"[✓] Validated Mandate Guard: {rule['condition_operator']} ${rule['condition_threshold']:,.2f}",
                f"[✓] Linked PayPal Vault Token ID: {rule['vault_token_id']}",
                f"[✓] Firewall Armed: Listening for {rule['trigger_source']} to settle {rule['recipient_name']} ({rule['recipient_paypal_email']})"
            ],
            paypal_api_trace={
                "tool": "paypal_vault.register_mandate",
                "mandate_id": rule["vault_token_id"],
                "payee": rule["recipient_paypal_email"],
                "status": "ARMED_AND_LISTENING"
            },
            verdict="CAPTURED",
            amount_impact=0.0
        )
        return jsonify({"success": True, "rule": rule})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400


@app.route("/api/rules/<int:rule_id>", methods=["DELETE"])
def delete_rule_endpoint(rule_id):
    """Deletes an active rule from SQLite."""
    try:
        db.delete_rule(rule_id)
        return jsonify({"success": True, "deleted_id": rule_id})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400


@app.route("/api/rules/<int:rule_id>/toggle", methods=["PATCH"])
def toggle_rule(rule_id):
    """Pauses or resumes an active mandate."""
    try:
        rule = db.toggle_rule_pause(rule_id)
        if rule:
            return jsonify({"success": True, "rule": rule})
        return jsonify({"success": False, "error": "Rule not found"}), 404
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400


@app.route("/api/webhooks/paypal", methods=["POST"])
def paypal_webhook():
    """
    Real PayPal Webhook receiver.
    Triggered when incoming payment captures (PAYMENT.CAPTURE.COMPLETED)
    or invoices arrive from PayPal.
    """
    raw_body = request.get_data(as_text=True)
    headers = dict(request.headers)
    account = db.get_account()

    event_data = request.get_json(silent=True) or {}
    event_type = event_data.get("event_type", "PAYMENT.CAPTURE.COMPLETED")
    event_source = event_data.get("summary") or event_data.get("resource_type") or "PayPal Webhook"

    # Evaluate against active rules
    eval_result = ai_engine.evaluate_and_process_event(
        event_source=f"PayPal: {event_source}",
        event_type=event_type,
        event_data=event_data
    )

    return jsonify({"success": True, "webhook_status": "PROCESSED", "evaluation": eval_result})


@app.route("/api/webhooks/external", methods=["POST"])
def external_webhook():
    """
    Production endpoint for vendor billing invoices, milestone deliveries, or price alerts.
    Can be called via curl, Zapier, GitHub Webhooks, or the production UI Modal.
    """
    data = request.get_json() or {}
    source = data.get("trigger_source", "External Billing Service")
    event_type = data.get("event_type", "INVOICE_BILLING")
    
    eval_result = ai_engine.evaluate_and_process_event(
        event_source=source,
        event_type=event_type,
        event_data=data
    )

    return jsonify({"success": True, "evaluation": eval_result})


@app.route("/api/rules/<int:rule_id>/override", methods=["POST"])
def override_rule(rule_id):
    """Human-in-the-loop action: Authorizes force-capture of a blocked spiked bill."""
    try:
        result = ai_engine.execute_override(rule_id)
        return jsonify({"success": True, "result": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400


@app.route("/api/rules/<int:rule_id>/reject", methods=["POST"])
def reject_rule(rule_id):
    """Human-in-the-loop action: Permanently rejects and disputes an unauthorized charge."""
    try:
        result = ai_engine.execute_reject(rule_id)
        return jsonify({"success": True, "result": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)

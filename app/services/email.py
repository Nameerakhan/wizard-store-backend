"""
Email service using Resend API.
Gracefully skips if RESEND_API_KEY is not configured.
"""

import json
import logging
import os
from typing import Any

import httpx

logger = logging.getLogger("wizard_store.email")

RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
FROM_EMAIL = os.getenv("FROM_EMAIL", "Wizard Store <orders@wizardstore.ai>")
RESEND_URL = "https://api.resend.com/emails"


async def send_order_confirmation(
    *,
    to_email: str,
    order_id: str,
    items: list[dict[str, Any]],
    subtotal: float,
    shipping_cost: float,
    total: float,
    shipping_address: dict[str, Any],
) -> None:
    """Send an order confirmation email. Silently skips if RESEND_API_KEY not set."""
    if not RESEND_API_KEY:
        logger.warning("RESEND_API_KEY not set — skipping confirmation email for order %s", order_id)
        return

    short_id = order_id[:8].upper()
    items_html = "".join(
        f"<tr>"
        f"<td style='padding:6px 0;color:#d1d5db;'>{i['product_name']} × {i['quantity']}</td>"
        f"<td style='padding:6px 0;color:#d1d5db;text-align:right;'>${float(i['product_price']) * i['quantity']:.2f}</td>"
        f"</tr>"
        for i in items
    )
    items_text = "\n".join(
        f"  {i['product_name']} × {i['quantity']}  —  ${float(i['product_price']) * i['quantity']:.2f}"
        for i in items
    )
    addr = shipping_address
    addr_line = f"{addr.get('line1', '')}{', ' + addr['line2'] if addr.get('line2') else ''}"
    addr_full = f"{addr_line}, {addr.get('city', '')}, {addr.get('state', '')} {addr.get('postal_code', '')}, {addr.get('country', '')}"

    html = f"""
    <div style="font-family:sans-serif;max-width:560px;margin:0 auto;background:#0f0a1e;color:#e5e7eb;padding:32px;border-radius:12px;">
      <h1 style="color:#D4AF37;margin-bottom:4px;">✨ Order Confirmed!</h1>
      <p style="color:#9ca3af;margin-top:0;">Order <strong style="color:#fff;">#{short_id}</strong></p>

      <p>Hi {addr.get('full_name', 'there')},<br>
      Your Wizard Store order has been received and is being prepared.</p>

      <table style="width:100%;border-collapse:collapse;margin:20px 0;">
        <thead>
          <tr style="border-bottom:1px solid #374151;">
            <th style="padding:8px 0;text-align:left;color:#9ca3af;font-weight:600;">Item</th>
            <th style="padding:8px 0;text-align:right;color:#9ca3af;font-weight:600;">Price</th>
          </tr>
        </thead>
        <tbody>{items_html}</tbody>
        <tfoot>
          <tr style="border-top:1px solid #374151;">
            <td style="padding:8px 0;color:#9ca3af;">Subtotal</td>
            <td style="padding:8px 0;text-align:right;color:#9ca3af;">${subtotal:.2f}</td>
          </tr>
          <tr>
            <td style="padding:4px 0;color:#9ca3af;">Shipping</td>
            <td style="padding:4px 0;text-align:right;color:{'#34d399' if shipping_cost == 0 else '#9ca3af'};">
              {'FREE' if shipping_cost == 0 else f'${shipping_cost:.2f}'}
            </td>
          </tr>
          <tr>
            <td style="padding:8px 0;font-weight:700;color:#fff;">Total</td>
            <td style="padding:8px 0;text-align:right;font-weight:700;color:#D4AF37;">${total:.2f}</td>
          </tr>
        </tfoot>
      </table>

      <div style="background:#1a1030;border-radius:8px;padding:16px;margin:20px 0;">
        <p style="margin:0 0 4px;font-weight:600;color:#fff;">Shipping to</p>
        <p style="margin:0;color:#9ca3af;">{addr.get('full_name', '')}<br>{addr_full}</p>
      </div>

      <p style="color:#6b7280;font-size:13px;">
        No payment was charged — this is a demo order.
        Payment processing will be enabled in a future update.
      </p>
    </div>
    """

    text = f"""Order #{short_id} Confirmed ✨

Hi {addr.get('full_name', 'there')},
Your Wizard Store order has been received.

ITEMS:
{items_text}

Subtotal: ${subtotal:.2f}
Shipping: {'FREE' if shipping_cost == 0 else f'${shipping_cost:.2f}'}
Total: ${total:.2f}

Shipping to: {addr_full}

No payment was charged — this is a demo order.
"""

    payload = {
        "from": FROM_EMAIL,
        "to": [to_email],
        "subject": f"Your Wizard Store order #{short_id} is confirmed! ✨",
        "html": html,
        "text": text,
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                RESEND_URL,
                headers={"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"},
                content=json.dumps(payload),
            )
            if resp.status_code == 200:
                logger.info("Confirmation email sent | order=%s to=%s", short_id, to_email)
            else:
                logger.warning("Resend returned %s for order %s: %s", resp.status_code, short_id, resp.text)
    except Exception as exc:
        logger.warning("Failed to send confirmation email for order %s: %s", short_id, exc)

"""
Email Notification Service — Kalnur
Sends transactional emails via Resend API.

Email types:
- welcome          : Sent on signup
- meal_reminder    : Breakfast, lunch, dinner reminders (daily)
- streak_at_risk   : User has a streak but hasn't logged today (8pm WAT)
- streak_milestone : User hits 3, 7, 14, 30-day streak
- weekly_summary   : Sunday evening recap
- re_engagement    : User inactive for 3+ days
"""

import os
import logging
import resend

logger = logging.getLogger(__name__)

RESEND_API_KEY  = os.getenv("RESEND_API_KEY", "")
FROM_EMAIL      = "Kally from Kalnur <hello@kalnur.com>"
APP_URL         = "https://kalnur.com"

# ── Colours matching Kalnur brand ─────────────────────────────────────────────
GREEN       = "#1B4332"
GREEN_MID   = "#2D6A4F"
GREEN_LIGHT = "#52976E"
GOLD        = "#C8860A"
BG          = "#F7F2EB"
DARK        = "#1A1208"
TEXT_MUTED  = "#7A6A58"


def _send(to: str, subject: str, html: str, include_unsubscribe: bool = False) -> bool:
    """Low-level send. Returns True on success, False on failure."""
    if not RESEND_API_KEY:
        logger.warning("RESEND_API_KEY not set — skipping email send")
        return False
    try:
        resend.api_key = RESEND_API_KEY
        payload = {
            "from": FROM_EMAIL,
            "to": to,
            "subject": subject,
            "html": html,
        }
        if include_unsubscribe:
            unsubscribe_url = f"{APP_URL}/api/v1/unsubscribe?email={to}"
            payload["headers"] = {
                "List-Unsubscribe": f"<{unsubscribe_url}>",
                "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
            }
        resend.Emails.send(payload)
        return True
    except Exception as e:
        logger.warning("Email send failed to %s: %s", to, e)
        return False


def _base_template(body_content: str, to: str = "") -> str:
    """Wraps content in Kalnur-branded email layout."""
    unsubscribe_link = f'<p style="font-size:11px;color:{TEXT_MUTED};margin:6px 0 0;">Don\'t want these emails? <a href="{APP_URL}/api/v1/unsubscribe?email={to}" style="color:{TEXT_MUTED};text-decoration:underline;">Unsubscribe</a></p>' if to else ""
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
    </head>
    <body style="margin:0;padding:0;background:{BG};font-family:'Poppins',Arial,sans-serif;">
      <table width="100%" cellpadding="0" cellspacing="0" style="background:{BG};padding:32px 16px;">
        <tr>
          <td align="center">
            <table width="100%" cellpadding="0" cellspacing="0" style="max-width:520px;">

              <!-- Header -->
              <tr>
                <td align="center" style="padding-bottom:24px;">
                  <span style="font-size:28px;">🌱</span>
                  <span style="font-size:20px;font-weight:800;color:{GREEN};letter-spacing:2px;margin-left:8px;">KALNUR</span>
                </td>
              </tr>

              <!-- Card -->
              <tr>
                <td style="background:#ffffff;border-radius:20px;padding:32px;box-shadow:0 4px 24px rgba(0,0,0,0.07);">
                  {body_content}
                </td>
              </tr>

              <!-- Footer -->
              <tr>
                <td align="center" style="padding-top:24px;">
                  <p style="font-size:11px;color:{TEXT_MUTED};margin:0;">
                    © 2026 Kalnur Nutrition Intelligence ·
                    <a href="{APP_URL}" style="color:{GREEN_LIGHT};text-decoration:none;">kalnur.com</a>
                  </p>
                  {unsubscribe_link}
                </td>
              </tr>

            </table>
          </td>
        </tr>
      </table>
    </body>
    </html>
    """


def _cta_button(text: str, url: str) -> str:
    return f"""
    <a href="{url}" style="
      display:inline-block;margin-top:24px;
      background:{GREEN};color:#ffffff;
      padding:14px 32px;border-radius:12px;
      font-size:15px;font-weight:700;text-decoration:none;
      box-shadow:0 4px 16px rgba(27,67,50,0.3);
    ">{text}</a>
    """


# ══════════════════════════════════════════════════════════════════════════════
# EMAIL SENDERS
# ══════════════════════════════════════════════════════════════════════════════

def send_welcome_email(to: str, name: str) -> bool:
    """Sent immediately after a user signs up."""
    first = name.split()[0] if name else "there"
    body = f"""
    <h1 style="font-size:24px;font-weight:800;color:{DARK};margin:0 0 8px;">
      Welcome to Kalnur, {first}! 🌱
    </h1>
    <p style="font-size:15px;color:{TEXT_MUTED};line-height:1.7;margin:0 0 16px;">
      Hey {first}, Kally here — your personal nutrition coach.
    </p>
    <p style="font-size:15px;color:{TEXT_MUTED};line-height:1.7;margin:0 0 8px;">
      You've just taken the first step toward eating with intelligence. Here's what you can do:
    </p>
    <ul style="font-size:14px;color:{DARK};line-height:2;padding-left:20px;margin:0 0 16px;">
      <li>📸 Snap a photo of any meal — Kally identifies it instantly</li>
      <li>📊 Track the nutrients that actually matter for your goal</li>
      <li>💬 Chat with Kally anytime for personalised coaching</li>
      <li>🔥 Build a logging streak and stay consistent</li>
    </ul>
    <p style="font-size:14px;color:{TEXT_MUTED};margin:0;">
      Log your first meal and let's get started 👇
    </p>
    {_cta_button("Log Your First Meal 🍛", APP_URL)}
    """
    return _send(to, f"Welcome to Kalnur, {first}! 🌱", _base_template(body, to))


def send_meal_reminder_email(to: str, name: str, meal_type: str) -> bool:
    """Breakfast / lunch / dinner reminder."""
    first = name.split()[0] if name else "there"
    emojis = {"breakfast": "🍳", "lunch": "🍛", "dinner": "🍽️"}
    emoji = emojis.get(meal_type, "🍴")
    body = f"""
    <h1 style="font-size:24px;font-weight:800;color:{DARK};margin:0 0 8px;">
      {emoji} Time to log your {meal_type}!
    </h1>
    <p style="font-size:15px;color:{TEXT_MUTED};line-height:1.7;margin:0 0 16px;">
      Hey {first}! Don't forget to log your {meal_type} today.
    </p>
    <p style="font-size:14px;color:{TEXT_MUTED};line-height:1.7;margin:0;">
      Staying consistent with logging is the fastest way to hit your goal.
      Kally is ready to analyse your meal 👇
    </p>
    {_cta_button(f"Log {meal_type.capitalize()} Now {emoji}", f"{APP_URL}/log/camera")}
    """
    return _send(to, f"Don't forget to log your {meal_type} today {emoji}", _base_template(body, to), include_unsubscribe=True)


def send_streak_at_risk_email(to: str, name: str, streak: int) -> bool:
    """Sent at 8pm WAT when user has a streak but hasn't logged today."""
    first = name.split()[0] if name else "there"
    body = f"""
    <h1 style="font-size:24px;font-weight:800;color:{DARK};margin:0 0 8px;">
      Your {streak}-day streak is at risk! 🔥
    </h1>
    <p style="font-size:15px;color:{TEXT_MUTED};line-height:1.7;margin:0 0 16px;">
      Hey {first}! You've been on a {streak}-day logging streak — that's incredible.
    </p>
    <p style="font-size:14px;color:{TEXT_MUTED};line-height:1.7;margin:0;">
      But you haven't logged a meal today yet. Midnight is approaching —
      log one meal now to keep your streak alive 👇
    </p>
    {_cta_button("Protect My Streak 🔥", f"{APP_URL}/log/camera")}
    """
    return _send(to, f"Your {streak}-day streak is at risk, {first}! 🔥", _base_template(body, to), include_unsubscribe=True)


def send_streak_milestone_email(to: str, name: str, streak: int) -> bool:
    """Sent when user hits 3, 7, 14, or 30-day streak."""
    first = name.split()[0] if name else "there"
    milestones = {
        3:  ("You're on a roll! 🌱",  "3 days in a row — you're building a real habit."),
        7:  ("One full week! 🔥",      "7 days straight — one full week of tracking. Kally is proud of you!"),
        14: ("Two weeks strong! 💪",   "14 days in a row — you're in the top 10% of Kalnur users!"),
        30: ("30 days — legend! 🏆",   "A full month of logging. You've completely transformed your nutrition awareness!"),
    }
    title, message = milestones.get(streak, (f"{streak}-day streak! 🔥", f"{streak} days of consistent logging — amazing!"))
    body = f"""
    <h1 style="font-size:24px;font-weight:800;color:{DARK};margin:0 0 8px;">
      🎉 {title}
    </h1>
    <p style="font-size:15px;color:{TEXT_MUTED};line-height:1.7;margin:0 0 16px;">
      Hey {first}! {message}
    </p>
    <div style="background:{BG};border-radius:14px;padding:20px;text-align:center;margin:16px 0;">
      <div style="font-size:48px;margin-bottom:8px;">🔥</div>
      <div style="font-size:36px;font-weight:800;color:{GREEN};">{streak} Days</div>
      <div style="font-size:13px;color:{TEXT_MUTED};margin-top:4px;">Logging Streak</div>
    </div>
    <p style="font-size:14px;color:{TEXT_MUTED};line-height:1.7;margin:0;">
      Keep it going — log today's meals to extend your streak 👇
    </p>
    {_cta_button("Keep the Streak Going 🌱", APP_URL)}
    """
    return _send(to, f"🎉 {streak}-day streak — {title}", _base_template(body, to), include_unsubscribe=True)


def send_weekly_summary_email(
    to: str,
    name: str,
    days_logged: int,
    best_streak: int,
    avg_calories: float,
    calorie_goal: float,
    top_meal: str | None,
) -> bool:
    """Sent every Sunday evening with a weekly recap."""
    first = name.split()[0] if name else "there"
    pct = int((avg_calories / calorie_goal) * 100) if calorie_goal > 0 else 0

    if days_logged >= 6:
        headline = f"Incredible week, {first}! 🏆"
        sub = "You logged almost every day — consistency like this gets real results."
    elif days_logged >= 4:
        headline = f"Solid week, {first}! 💪"
        sub = "You logged most of your meals — keep building that habit."
    else:
        headline = f"Let's do better this week, {first} 🌱"
        sub = "Every meal logged is a step closer to your goal. Let's aim for 5+ days next week!"

    top_meal_row = f"""
    <tr>
      <td style="padding:8px 0;border-bottom:1px solid {BG};">
        <span style="font-size:13px;color:{TEXT_MUTED};">🍛 Most logged meal</span>
        <span style="float:right;font-size:13px;font-weight:600;color:{DARK};">{top_meal}</span>
      </td>
    </tr>
    """ if top_meal else ""

    body = f"""
    <h1 style="font-size:24px;font-weight:800;color:{DARK};margin:0 0 8px;">
      {headline}
    </h1>
    <p style="font-size:15px;color:{TEXT_MUTED};line-height:1.7;margin:0 0 24px;">
      {sub}
    </p>

    <!-- Stats table -->
    <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:16px;">
      <tr>
        <td style="padding:8px 0;border-bottom:1px solid {BG};">
          <span style="font-size:13px;color:{TEXT_MUTED};">📅 Days logged</span>
          <span style="float:right;font-size:13px;font-weight:600;color:{DARK};">{days_logged} / 7 days</span>
        </td>
      </tr>
      <tr>
        <td style="padding:8px 0;border-bottom:1px solid {BG};">
          <span style="font-size:13px;color:{TEXT_MUTED};">🔥 Best streak this week</span>
          <span style="float:right;font-size:13px;font-weight:600;color:{DARK};">{best_streak} days</span>
        </td>
      </tr>
      <tr>
        <td style="padding:8px 0;border-bottom:1px solid {BG};">
          <span style="font-size:13px;color:{TEXT_MUTED};">🔥 Avg daily calories</span>
          <span style="float:right;font-size:13px;font-weight:600;color:{DARK};">{int(avg_calories)} / {int(calorie_goal)} kcal ({pct}%)</span>
        </td>
      </tr>
      {top_meal_row}
    </table>

    <p style="font-size:14px;color:{TEXT_MUTED};margin:0;">
      Start the new week strong 👇
    </p>
    {_cta_button("Open Kalnur 🌱", APP_URL)}
    """
    return _send(to, f"Your Kalnur week in review 📊", _base_template(body, to), include_unsubscribe=True)


def send_missing_food_email(
    to: str,
    name: str,
    missing_foods: list[str],
    logged_foods: list[str],
) -> bool:
    """
    Sent immediately when a manually added food is not found in the KB.

    Two scenarios:
    - Some foods logged + some missing → partial success message
    - All foods missing → full miss message
    """
    first = name.split()[0] if name else "there"
    missing_list = ", ".join(f"<strong>{f.title()}</strong>" for f in missing_foods)
    all_missing = len(logged_foods) == 0

    if all_missing:
        headline = f"I couldn't log your meal yet, {first}"
        intro = f"""
        <p style="font-size:15px;color:{TEXT_MUTED};line-height:1.7;margin:0 0 16px;">
            You added {missing_list} — but I don't have enough nutritional data
            for {'it' if len(missing_foods) == 1 else 'them'} yet.
        </p>
        <p style="font-size:15px;color:{TEXT_MUTED};line-height:1.7;margin:0 0 16px;">
            I've flagged {'it' if len(missing_foods) == 1 else 'them'} and we're working on adding
            {'it' if len(missing_foods) == 1 else 'them'} to our database.
            I'll send you an email as soon as {'it is' if len(missing_foods) == 1 else 'they are'} ready — then you can log it with full nutrition accuracy.
        </p>
        """
    else:
        logged_list = ", ".join(f"<strong>{f.title()}</strong>" for f in logged_foods)
        headline = f"Almost there, {first} — one thing to flag"
        intro = f"""
        <p style="font-size:15px;color:{TEXT_MUTED};line-height:1.7;margin:0 0 16px;">
            I logged your {logged_list} with full nutrition data.
        </p>
        <p style="font-size:15px;color:{TEXT_MUTED};line-height:1.7;margin:0 0 16px;">
            But I don't have enough data for {missing_list} yet, so
            {'it was' if len(missing_foods) == 1 else 'they were'} left out of this meal.
            I've flagged {'it' if len(missing_foods) == 1 else 'them'} — we're working on adding
            {'it' if len(missing_foods) == 1 else 'them'} to our database and I'll let you know when it's done.
        </p>
        """

    body = f"""
    <h1 style="font-size:22px;font-weight:800;color:{DARK};margin:0 0 16px;">
        {headline}
    </h1>
    {intro}
    <div style="background:{BG};border-radius:12px;padding:16px 20px;margin:0 0 20px;">
        <p style="font-size:12px;font-weight:700;color:{TEXT_MUTED};text-transform:uppercase;letter-spacing:0.06em;margin:0 0 6px;">
            Not in our database yet
        </p>
        <p style="font-size:15px;color:{DARK};font-weight:600;margin:0;">
            {missing_list}
        </p>
    </div>
    <p style="font-size:13px;color:{TEXT_MUTED};line-height:1.6;margin:0;">
        We care about getting your nutrition right — logging with incomplete data
        would give you inaccurate numbers, and that defeats the point.
        We'd rather be honest and fix it properly.
    </p>
    """
    subject = (
        f"About {missing_foods[0].title()} — we're on it"
        if len(missing_foods) == 1
        else f"We're missing data for {len(missing_foods)} foods you added"
    )
    return _send(to, subject, _base_template(body, to), include_unsubscribe=True)


def send_reengagement_email(to: str, name: str, days_inactive: int) -> bool:
    """Sent when user hasn't logged in 3+ days."""
    first = name.split()[0] if name else "there"
    body = f"""
    <h1 style="font-size:24px;font-weight:800;color:{DARK};margin:0 0 8px;">
      Kally misses you, {first} 👀
    </h1>
    <p style="font-size:15px;color:{TEXT_MUTED};line-height:1.7;margin:0 0 16px;">
      You haven't logged a meal in {days_inactive} days — and that's okay!
      Life gets busy. But your nutrition goals are still waiting for you.
    </p>
    <p style="font-size:14px;color:{TEXT_MUTED};line-height:1.7;margin:0;">
      Come back and log just one meal today. That's all it takes to get back on track 👇
    </p>
    {_cta_button("Come Back to Kalnur 🌱", APP_URL)}
    """
    return _send(to, f"Kally misses you, {first} 👀", _base_template(body, to), include_unsubscribe=True)

"""Data Cleaner Studio — shared AI / app settings (v1.3, Batch 3).

The ONE place the Groq/OpenAI-compatible API key lives. The key is kept
in a local ``settings.json`` file next to the app — never baked into code,
never sent anywhere except the chat endpoint the user chose.

Contract (Batch 5, natural-language questions, imports this module too —
keep these names and signatures exactly as they are):
  - load_settings() -> dict
  - save_settings(d)
  - get_api_key() -> str | None
  - ask_ai(prompt, system="...") -> str
  - render_settings(st)

Settings file keys:
  groq_api_key : the user's Groq API key ("" when not set)
  theme        : "Dark green" | "Dark blue" | "Light"
  language     : "en" | "hi" | "ur"
  fx_rates     : {"INR": 1.0, "USD": 83.0, "EUR": 90.0, "GBP": 105.0}
                 (fixed estimates, edited in the currency screen)
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path

SETTINGS_PATH = Path(__file__).resolve().parent / "settings.json"

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.3-70b-versatile"

DEFAULT_SETTINGS = {
    "groq_api_key": "",
    "theme": "Dark green",
    "language": "en",
    "fx_rates": {"INR": 1.0, "USD": 83.0, "EUR": 90.0, "GBP": 105.0},
}

NO_KEY_ERROR = (
    "No Groq API key set. Open Settings and paste your Groq API key first — "
    "AI insights need a key before they can run."
)


def _settings_file(path=None) -> Path:
    return Path(path) if path is not None else SETTINGS_PATH


def load_settings(path=None) -> dict:
    """Read settings.json (next to the app). Missing or broken file ->
    the defaults, so the app never crashes on a first launch."""
    settings = dict(DEFAULT_SETTINGS)
    settings["fx_rates"] = dict(DEFAULT_SETTINGS["fx_rates"])
    try:
        stored = json.loads(_settings_file(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return settings
    if isinstance(stored, dict):
        for key, value in stored.items():
            if key == "fx_rates" and isinstance(value, dict):
                merged = dict(DEFAULT_SETTINGS["fx_rates"])
                merged.update({str(k).upper(): float(v)
                               for k, v in value.items()})
                settings["fx_rates"] = merged
            else:
                settings[key] = value
    return settings


def save_settings(d: dict, path=None) -> None:
    """Write the settings dict to settings.json (next to the app).
    Only ever writes what the caller passed — the API key is stored
    exactly as typed, nothing else is added."""
    _settings_file(path).write_text(
        json.dumps(dict(d), indent=2, ensure_ascii=False),
        encoding="utf-8")


def get_api_key(path=None) -> str | None:
    """The saved Groq API key, or None when none is set. Blank/whitespace
    counts as not set."""
    key = load_settings(path).get("groq_api_key") or ""
    key = str(key).strip()
    return key or None


def _build_request(prompt: str, system: str, api_key: str) -> urllib.request.Request:
    """The exact POST the chat endpoint receives — kept separate so tests
    can check the request without calling the real API."""
    body = json.dumps({
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.7,
        "max_tokens": 600,
    }).encode("utf-8")
    return urllib.request.Request(
        GROQ_URL, data=body,
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {api_key}"},
        method="POST")


def ask_ai(prompt: str,
           system: str = ("You are a friendly data analyst. Explain what "
                          "the data says in plain, simple English. Keep it "
                          "short — one paragraph. Never invent numbers that "
                          "are not in the prompt.")) -> str:
    """Ask the chat endpoint one question and return its plain-text reply.

    Raises ValueError naming exactly what is missing when no API key is
    set, and RuntimeError with the endpoint's message when the call fails.
    """
    api_key = get_api_key()
    if not api_key:
        raise ValueError(NO_KEY_ERROR)
    if not str(prompt).strip():
        raise ValueError("Nothing to ask — the prompt is empty.")
    request = _build_request(str(prompt), str(system), api_key)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read().decode("utf-8", errors="replace"))
            message = detail.get("error", {}).get("message", "")
        except Exception:
            message = ""
        raise RuntimeError(
            f"AI service returned HTTP {e.code}"
            + (f": {message}" if message else
               " — check the API key in Settings.")) from e
    except urllib.error.URLError as e:
        raise RuntimeError(
            f"Could not reach the AI service ({e.reason}). Check your "
            "internet connection and try again.") from e
    try:
        text = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        raise RuntimeError(
            "AI service replied in a form this app does not understand.") from e
    return str(text).strip()


# --------------------------------------------------------------------------
# render function — thin Streamlit wrapper (st passed in, never imported)
# --------------------------------------------------------------------------

def render_settings(st) -> None:
    """Settings screen: paste the Groq API key, save it, and test it.

    Belongs in the sidebar (under "Load your data") or at the top of the
    Tools tab — wherever the coordinator puts it, it only reads/writes
    settings.json and never touches the data. The key field is a password
    input, so the key is never shown on screen."""
    st.subheader("Settings")
    st.write("AI insights need a Groq API key. Get one free at "
             "console.groq.com, paste it here, and it is saved on this "
             "computer only (settings.json next to the app). The key is "
             "never sent anywhere except Groq's chat endpoint.")
    current = get_api_key() or ""
    typed = st.text_input("Groq API key", value=current, type="password",
                          key="ai_key_input",
                          help="Starts with gsk_ — paste the whole key.")
    if st.button("Save settings", key="ai_key_save"):
        settings = load_settings()
        settings["groq_api_key"] = typed.strip()
        save_settings(settings)
        if typed.strip():
            st.success("Saved — your API key is stored on this computer.")
        else:
            st.info("Saved — the API key field is now empty, so AI "
                    "insights are off until you paste a key.")
    if st.button("Test the key", key="ai_key_test"):
        if not typed.strip():
            st.error(NO_KEY_ERROR)
        else:
            settings = load_settings()
            settings["groq_api_key"] = typed.strip()
            save_settings(settings)
            try:
                reply = ask_ai("Reply with the single word OK and nothing else.")
                st.success(f"Key works — the service replied: {reply}")
            except Exception as e:  # noqa: BLE001 - show the error, don't crash
                st.error(str(e))

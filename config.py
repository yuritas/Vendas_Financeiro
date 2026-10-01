"""Configuração central — tudo vem do arquivo .env."""
import os
from dotenv import load_dotenv

load_dotenv()


def _list(name: str, default: str) -> list[str]:
    return [s.strip() for s in os.getenv(name, default).split(",") if s.strip()]


def _bool(name: str, default: str) -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "sim", "yes")


# --- MetaTrader 5 ---
MT5_LOGIN = int(os.getenv("MT5_LOGIN", "0") or 0)
MT5_PASSWORD = os.getenv("MT5_PASSWORD", "")
MT5_SERVER = os.getenv("MT5_SERVER", "")
MT5_PATH = os.getenv("MT5_PATH") or None          # caminho do terminal64.exe (opcional)
SYMBOLS = _list("SYMBOLS", "EURUSD,GBPUSD,USDJPY,AUDUSD,USDCAD,USDCHF,NZDUSD,EURJPY,GBPJPY")
SYMBOL_SUFFIX = os.getenv("SYMBOL_SUFFIX", "")    # ex.: ".a", "m" — depende da corretora
MAGIC = int(os.getenv("MAGIC", "260901"))

# --- Segurança: em DRY_RUN nenhuma ordem real é enviada (opera em modo simulado/papel) ---
DRY_RUN = _bool("DRY_RUN", "true")

# --- Execução ---
# auto     = abre a ordem sozinho e reporta no WhatsApp/web
# confirm  = cria o sinal e espera "SIM <id>"
EXECUTION_MODE = os.getenv("EXECUTION_MODE", "auto").strip().lower()
# Trava extra: em conta REAL com modo auto e DRY_RUN=false, só envia ordens se isto for true
ALLOW_REAL_AUTO = _bool("ALLOW_REAL_AUTO", "false")

# --- Aprendizado ---
LEARNING_ENABLED = _bool("LEARNING_ENABLED", "true")
LEARN_MIN_TRADES = int(os.getenv("LEARN_MIN_TRADES", "20"))     # amostra mínima p/ mexer em pesos
LEARN_WINDOW = int(os.getenv("LEARN_WINDOW", "60"))             # últimos N trades analisados
SYMBOL_MIN_TRADES = int(os.getenv("SYMBOL_MIN_TRADES", "8"))    # amostra mínima por par
MAX_CONSEC_LOSSES = int(os.getenv("MAX_CONSEC_LOSSES", "3"))    # perdas seguidas -> reduz risco

# --- Relatórios ---
TIMEZONE = os.getenv("TIMEZONE", "America/Sao_Paulo")
DAILY_REPORT_HOUR = int(os.getenv("DAILY_REPORT_HOUR", "18"))   # hora local do resumo diário

# --- Risco ---
RISK_PER_TRADE = float(os.getenv("RISK_PER_TRADE", "0.5"))     # % do saldo arriscado por trade
MAX_OPEN_TRADES = int(os.getenv("MAX_OPEN_TRADES", "3"))
MAX_DAILY_LOSS = float(os.getenv("MAX_DAILY_LOSS", "2.0"))     # % do saldo; ao atingir, pausa
MAX_SPREAD_POINTS = int(os.getenv("MAX_SPREAD_POINTS", "30"))
ATR_PERIOD = int(os.getenv("ATR_PERIOD", "14"))
SL_ATR_MULT = float(os.getenv("SL_ATR_MULT", "1.5"))
TP_ATR_MULT = float(os.getenv("TP_ATR_MULT", "3.0"))

# --- Sinais ---
SIGNAL_THRESHOLD = float(os.getenv("SIGNAL_THRESHOLD", "3.0"))  # |score do par| mínimo
SIGNAL_EXPIRY_MIN = int(os.getenv("SIGNAL_EXPIRY_MIN", "15"))
ANALYSIS_INTERVAL_MIN = int(os.getenv("ANALYSIS_INTERVAL_MIN", "15"))
NEWS_BLACKOUT_MIN = int(os.getenv("NEWS_BLACKOUT_MIN", "30"))   # sem novas ordens perto de notícia forte

# Pesos de cada pilar na nota por moeda
W_CALENDAR = float(os.getenv("W_CALENDAR", "1.0"))
W_NEWS = float(os.getenv("W_NEWS", "1.0"))
W_MACRO = float(os.getenv("W_MACRO", "1.0"))

# --- Fontes fundamentalistas ---
CALENDAR_URL = os.getenv("CALENDAR_URL", "https://nfs.faireconomy.media/ff_calendar_thisweek.json")
NEWS_FEEDS = _list("NEWS_FEEDS", "https://www.fxstreet.com/rss/news")
NEWS_LOOKBACK_HOURS = int(os.getenv("NEWS_LOOKBACK_HOURS", "12"))
MACRO_FILE = os.getenv("MACRO_FILE", "macro.json")

# --- IA (sentimento de notícias) ---
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5")

# --- WhatsApp (Meta Cloud API) ---
WA_TOKEN = os.getenv("WA_TOKEN", "")
WA_PHONE_NUMBER_ID = os.getenv("WA_PHONE_NUMBER_ID", "")
WA_VERIFY_TOKEN = os.getenv("WA_VERIFY_TOKEN", "")
WA_APP_SECRET = os.getenv("WA_APP_SECRET", "")
WA_API_VERSION = os.getenv("WA_API_VERSION", "v21.0")
WA_ALLOWED_NUMBERS = _list("WA_ALLOWED_NUMBERS", "")   # ex.: 5511999998888 (sem +)
WA_TEMPLATE_NAME = os.getenv("WA_TEMPLATE_NAME", "")   # template aprovado p/ fora da janela de 24h

# --- Web ---
WEB_HOST = os.getenv("WEB_HOST", "127.0.0.1")
WEB_PORT = int(os.getenv("WEB_PORT", "8000"))
WEB_TOKEN = os.getenv("WEB_TOKEN", "")

DB_PATH = os.getenv("DB_PATH", "forexbot.db")

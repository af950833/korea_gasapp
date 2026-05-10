"""Constants for Korea Gas App."""

DOMAIN = "korea_gasapp"

# ── Config-entry keys ────────────────────────────────────────────────────────
CONF_ACCOUNT_ID = "account_id"
CONF_ADID = "adid"
CONF_APP_VERSION = "app_version"
CONF_AUTH_TOKEN = "auth_token"
CONF_COMPANY_CODE = "company_code"
CONF_CUSTOMER_NO = "customer_no"
CONF_DEVICE_ID = "device_id"
CONF_DEVICE_NAME = "device_name"
CONF_MEMBER_NO = "member_no"
CONF_OS_VERSION = "os_version"
CONF_PLATFORM = "platform"
CONF_READING_ENTITY_ID = "reading_entity_id"
CONF_READING_ROUND = "reading_round"
CONF_TID = "tid"
CONF_USER_AGENT = "user_agent"
CONF_USE_CONTRACT_NUM = "use_contract_num"

# ── Reading-round option values ──────────────────────────────────────────────
READING_ROUND_UP = "ceil"
READING_ROUND_DOWN = "floor"
DEFAULT_READING_ROUND = READING_ROUND_UP

# ── Fixed daily schedule (local time) ───────────────────────────────────────
# Data refresh and auto self-reading submission both fire at this time.
FIXED_UPDATE_HOUR = 8
FIXED_UPDATE_MINUTE = 0
FIXED_UPDATE_SECOND = 0

# ── Gas App API defaults ─────────────────────────────────────────────────────
DEFAULT_API_BASE_URL = "https://app.gasapp.co.kr/api/"
DEFAULT_APP_PLATFORM = "android"
DEFAULT_APP_VERSION = "11.5.1492"
DEFAULT_USER_AGENT = "WunderFlo Appstore/11.5.1492"
DEFAULT_WEB_VERSION = "6.10.431"

# ── iOS client profile used during SMS login ─────────────────────────────────
# These values mirror the captured iOS app session so that the NICE identity
# verification and member-creation endpoints accept the request.
IOS_APP_VERSION = "4.3.7.27265"
IOS_DEVICE_NAME = "iPad"
IOS_OS_VERSION = "18.7"
IOS_PLATFORM = "IOS"
IOS_USER_AGENT = (
    "Mozilla/5.0 (iPad; CPU OS 18_7 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) WunderFlo iPhone/gasapp"
)

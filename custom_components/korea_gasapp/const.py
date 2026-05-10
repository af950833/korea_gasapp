"""Constants for Korea Gas App."""

DOMAIN = "korea_gasapp"

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

READING_ROUND_UP = "ceil"
READING_ROUND_DOWN = "floor"

DEFAULT_READING_ROUND = READING_ROUND_UP

# Fixed schedule: once a day at 08:00 local time.
# All polling and auto-submission use this time.
FIXED_UPDATE_HOUR = 8
FIXED_UPDATE_MINUTE = 0
FIXED_UPDATE_SECOND = 0

DEFAULT_API_BASE_URL = "https://app.gasapp.co.kr/api/"
DEFAULT_APP_PLATFORM = "android"
DEFAULT_APP_VERSION = "11.5.1492"
DEFAULT_USER_AGENT = "WunderFlo Appstore/11.5.1492"
DEFAULT_WEB_VERSION = "6.10.431"

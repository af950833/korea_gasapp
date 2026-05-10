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
CONF_MAX_READING_DELTA = "max_reading_delta"
CONF_OS_VERSION = "os_version"
CONF_PLATFORM = "platform"
CONF_POLL_INTERVAL = "poll_interval"
CONF_READING_ENTITY_ID = "reading_entity_id"
CONF_READING_ROUND = "reading_round"
CONF_SUBMIT_DAY = "submit_day"
CONF_SUBMIT_TIME = "submit_time"
CONF_TID = "tid"
CONF_USER_AGENT = "user_agent"
CONF_USE_CONTRACT_NUM = "use_contract_num"

READING_ROUND_UP = "ceil"
READING_ROUND_DOWN = "floor"

DEFAULT_POLL_INTERVAL = 60
DEFAULT_MAX_READING_DELTA = 500
DEFAULT_SUBMIT_DAY = 5
DEFAULT_SUBMIT_TIME = "08:00:00"
DEFAULT_READING_ROUND = READING_ROUND_UP

DEFAULT_API_BASE_URL = "https://app.gasapp.co.kr/api/"
DEFAULT_APP_PLATFORM = "android"
DEFAULT_APP_VERSION = "11.5.1492"
DEFAULT_USER_AGENT = "WunderFlo Appstore/11.5.1492"
DEFAULT_WEB_VERSION = "6.10.431"

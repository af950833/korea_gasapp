"""Client for the Korea Gas App backend."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin

from aiohttp import ClientSession

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_ACCOUNT_ID,
    CONF_ADID,
    CONF_APP_VERSION,
    CONF_AUTH_TOKEN,
    CONF_COMPANY_CODE,
    CONF_CUSTOMER_NO,
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_MEMBER_NO,
    CONF_OS_VERSION,
    CONF_PLATFORM,
    CONF_TID,
    CONF_USER_AGENT,
    CONF_USE_CONTRACT_NUM,
    DEFAULT_API_BASE_URL,
    DEFAULT_APP_PLATFORM,
    DEFAULT_APP_VERSION,
    DEFAULT_USER_AGENT,
    DEFAULT_WEB_VERSION,
)

_LOGGER = logging.getLogger(__name__)


# ── Exceptions ───────────────────────────────────────────────────────────────

class KoreaGasAppApiError(Exception):
    """Base error for all Gas App API failures."""


class KoreaGasAppAuthError(KoreaGasAppApiError):
    """Raised when authentication credentials are missing or expired."""


class KoreaGasAppEndpointUnknownError(KoreaGasAppApiError):
    """Raised when the HTTP session is unavailable (e.g. during config validation)."""


# ── Data models ──────────────────────────────────────────────────────────────

@dataclass(slots=True)
class BillDetail:
    """Parsed line-items from the current-month bill detail areas."""

    monthly_subtotal: int | None = None   # 당월 소계
    basic_charge: int | None = None
    usage_charge: int | None = None
    vat: int | None = None
    discount: int | None = None
    truncation: int | None = None
    unpaid: int | None = None
    usage_period: str | None = None
    due_date: str | None = None
    this_month_indicator: int | None = None
    last_month_indicator: int | None = None
    monthly_usage: int | None = None
    correction_factor: float | None = None
    correction_usage: float | None = None
    avg_calorific: float | None = None
    used_calorific: float | None = None
    meter_id: str | None = None
    reading_day: str | None = None
    reading_method: str | None = None
    prev_month_usage: str | None = None
    prev_year_usage: str | None = None
    discount_type: str | None = None


@dataclass(slots=True)
class CurrentBillSnapshot:
    """Current-month bill summary from relay/bills/month."""

    charge_krw: int | None = None
    title: str | None = None
    status: str | None = None
    payable: bool | None = None
    detail: BillDetail = field(default_factory=BillDetail)
    # All key-value rows from areaEtc / areaPayment / areaUnpayment / areaUsage,
    # stored as-is for display in HA attributes without any schema coupling.
    raw_areas: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class AnnualBillEntry:
    """One month's row from the annual bill history."""

    request_ym: str
    usage_qty: int | None = None
    charge_amt_qty: int | None = None


@dataclass(slots=True)
class IndicationHistoryEntry:
    """One entry from the self-reading history."""

    reading_date: str
    request_ym: str
    indicator: int | None = None
    method: str | None = None


@dataclass(slots=True)
class IndicationInfo:
    """Current indication window status from relay/indications."""

    last_month_indicator: int | None = None
    # True only during the open self-reading window; None when unknown.
    self_input_available: bool | None = None
    # True when the account has ever submitted a self-reading (derived from history).
    self_reading_registered: bool = False
    period_start: str | None = None
    period_end: str | None = None
    period_type: str | None = None
    request_ym: str | None = None


@dataclass(slots=True)
class GasUsageSnapshot:
    """All data fetched in one coordinator refresh cycle."""

    customer_no: str
    use_contract_num: str
    current_bill: CurrentBillSnapshot = field(default_factory=CurrentBillSnapshot)
    annual_bills: list[AnnualBillEntry] = field(default_factory=list)
    indication: IndicationInfo = field(default_factory=IndicationInfo)
    indication_history: list[IndicationHistoryEntry] = field(default_factory=list)


@dataclass(slots=True)
class MeterReadingSubmitResult:
    """Result returned by the self-reading submission endpoint."""

    input_yn: str | None = None
    error_code: str | None = None
    return_message: str | None = None
    last_month_indicator: int | None = None
    this_month_indicator: int | None = None
    expectation_charge: int | None = None
    usage: int | None = None


@dataclass(slots=True)
class SmsRequestResult:
    """IDs returned after requesting a NICE SMS verification code."""

    request_no: str
    response_uniq_id: str


@dataclass(slots=True)
class SmsConfirmResult:
    """CI/DI pair returned after a successful NICE SMS confirmation."""

    ci: str
    di: str


@dataclass(slots=True)
class MemberLoginResult:
    """Credentials returned after creating or re-registering a Gas App member."""

    member_no: str
    auth_token: str


# ── Key-map for bill detail parsing ─────────────────────────────────────────
# Maps Korean label → (BillDetail field name, parser tag).
# Parser tags:
#   "krw"   – Korean-won amount string  → int
#   "str"   – plain string (kept as-is)
#   "m3i"   – cubic-metre string        → int
#   "m3f"   – cubic-metre string        → float
#   "float" – plain numeric string      → float
#   ("float", "<suffix>") – strip suffix first, then parse as float
_BILL_DETAIL_KEY_MAP: dict[str, tuple[str, str | tuple[str, str]]] = {
    "당월 소계":      ("monthly_subtotal",    "krw"),
    "기본요금":       ("basic_charge",        "krw"),
    "사용요금":       ("usage_charge",        "krw"),
    "부가세":         ("vat",                 "krw"),
    "할인금액":       ("discount",            "krw"),
    "절사금액":       ("truncation",          "krw"),
    "미납 소계":      ("unpaid",              "krw"),
    "사용 기간":      ("usage_period",        "str"),
    "납부 마감일":    ("due_date",            "str"),
    "당월지침":       ("this_month_indicator","m3i"),
    "전월지침":       ("last_month_indicator","m3i"),
    "당월사용량":     ("monthly_usage",       "m3i"),
    "보정 계수":      ("correction_factor",   "float"),
    "보정량":         ("correction_usage",    "m3f"),
    "평균열량":       ("avg_calorific",       ("float", "MJ/m³")),
    "사용열량":       ("used_calorific",      ("float", "MJ")),
    "계량기 번호":    ("meter_id",            "str"),
    "검침일":         ("reading_day",         "str"),
    "검침방법":       ("reading_method",      "str"),
    "전월 사용량":    ("prev_month_usage",    "str"),
    "전년 동월 사용량": ("prev_year_usage",   "str"),
    "할인종류":       ("discount_type",       "str"),
}


# ── Client ───────────────────────────────────────────────────────────────────

class KoreaGasAppClient:
    """Async HTTP client for the Korea Gas App private API."""

    def __init__(
        self,
        session: ClientSession,
        *,
        account_id: str,
        customer_no: str,
        auth_token: str | None = None,
        member_no: str | None = None,
        company_code: str | None = None,
        use_contract_num: str | None = None,
        adid: str | None = None,
        tid: str | None = None,
        app_version: str | None = None,
        platform: str | None = None,
        os_version: str | None = None,
        device_name: str | None = None,
        device_id: str | None = None,
        user_agent: str | None = None,
        base_url: str = DEFAULT_API_BASE_URL,
    ) -> None:
        self._session = session
        self._account_id = account_id
        self._customer_no = customer_no
        self._auth_token = auth_token
        self._member_no = member_no
        self._company_code = company_code
        self._use_contract_num = use_contract_num
        self._adid = adid
        self._tid = tid
        self._app_version = app_version or DEFAULT_APP_VERSION
        self._platform = platform or DEFAULT_APP_PLATFORM
        self._os_version = os_version
        self._device_name = device_name
        self._device_id = device_id
        self._user_agent = user_agent or DEFAULT_USER_AGENT
        self._base_url = base_url

    @classmethod
    def from_config_entry(cls, hass: HomeAssistant, entry: ConfigEntry) -> KoreaGasAppClient:
        """Construct a client from a loaded config entry."""
        return cls(
            async_get_clientsession(hass),
            account_id=entry.data.get(CONF_ACCOUNT_ID, ""),
            customer_no=entry.data.get(CONF_CUSTOMER_NO, ""),
            auth_token=entry.data.get(CONF_AUTH_TOKEN),
            member_no=entry.data.get(CONF_MEMBER_NO),
            company_code=entry.data.get(CONF_COMPANY_CODE),
            use_contract_num=entry.data.get(CONF_USE_CONTRACT_NUM),
            adid=entry.data.get(CONF_ADID),
            tid=entry.data.get(CONF_TID),
            app_version=entry.data.get(CONF_APP_VERSION),
            platform=entry.data.get(CONF_PLATFORM),
            os_version=entry.data.get(CONF_OS_VERSION),
            device_name=entry.data.get(CONF_DEVICE_NAME),
            device_id=entry.data.get(CONF_DEVICE_ID),
            user_agent=entry.data.get(CONF_USER_AGENT),
        )

    # ── Credential validation ─────────────────────────────────────────────

    async def validate(self) -> None:
        """Raise KoreaGasAppAuthError when required credentials are absent."""
        if not self._customer_no and not self._use_contract_num:
            raise KoreaGasAppAuthError("Customer number or use contract number is required")
        if not self._auth_token or not self._member_no or not self._company_code:
            raise KoreaGasAppAuthError("X-TOKEN, X-MEMBER, and X-COMPANY values are required")

    # ── Main data fetch ───────────────────────────────────────────────────

    async def async_get_usage(self) -> GasUsageSnapshot:
        """Fetch all data needed to populate coordinator sensors."""
        await self.validate()

        current_bill = await self._async_get_current_bill()
        annual_bills = await self._async_get_annual_bills()
        indication = await self._async_get_indication()
        history = await self._async_get_indication_history()

        # Derive registration status from history: if any past entry used
        # "자가검침" method the account has signed up for the service.
        # Also treat an open input window (selfInputAvailable=True) as registered.
        history_registered = any(
            (item.method or "").strip() == "자가검침" for item in history
        )
        indication.self_reading_registered = (
            history_registered or indication.self_input_available is True
        )

        return GasUsageSnapshot(
            customer_no=self._customer_no,
            use_contract_num=self._use_contract_num or "",
            current_bill=current_bill,
            annual_bills=annual_bills,
            indication=indication,
            indication_history=history,
        )

    # ── Individual endpoint helpers ───────────────────────────────────────

    async def _async_get_current_bill(self) -> CurrentBillSnapshot:
        try:
            data = await self._get(
                "relay/bills/month",
                self._contract_params(),
            )
        except KoreaGasAppApiError as err:
            _LOGGER.warning("Could not fetch current bill: %s", err)
            return CurrentBillSnapshot()

        if not isinstance(data, dict):
            _LOGGER.warning("Unexpected current-bill response type: %s", type(data))
            return CurrentBillSnapshot()

        detail = BillDetail()
        raw_areas: dict[str, str] = {}

        all_areas = (
            data.get("areaEtc") or [],
            data.get("areaPayment") or [],
            data.get("areaUnpayment") or [],
            data.get("areaUsage") or [],
        )
        for area in all_areas:
            for item in area:
                if not isinstance(item, dict):
                    continue
                self._apply_bill_detail_item(detail, item)
                # Collect every key-value as-is for raw attribute display
                key = item.get("key", "")
                value = item.get("value", "")
                if key:
                    raw_areas[key] = value

        return CurrentBillSnapshot(
            charge_krw=_parse_krw(data.get("amount", "")),
            title=data.get("title"),
            status=data.get("status"),
            payable=data.get("payable") == "Y",
            detail=detail,
            raw_areas=raw_areas,
        )

    @staticmethod
    def _apply_bill_detail_item(detail: BillDetail, item: dict[str, Any]) -> None:
        """Parse one key-value row from a bill area and write it to detail."""
        label = item.get("key", "")
        raw_value = item.get("value", "")
        mapping = _BILL_DETAIL_KEY_MAP.get(label)
        if mapping is None:
            _LOGGER.debug("Unknown bill detail key (ignored): %r = %r", label, raw_value)
            return

        field_name, parser = mapping
        if parser == "krw":
            value = _parse_krw(raw_value)
        elif parser == "str":
            value = raw_value
        elif parser == "m3i":
            value = _parse_numeric_int(raw_value, strip_suffix="m³")
        elif parser == "m3f":
            value = _parse_numeric_float(raw_value, strip_suffix="m³")
        elif parser == "float":
            value = _parse_numeric_float(raw_value)
        elif isinstance(parser, tuple):
            # ("float", "<suffix>") — strip the unit suffix before parsing
            _, suffix = parser
            value = _parse_numeric_float(raw_value, strip_suffix=suffix)
        else:
            return

        setattr(detail, field_name, value)

    async def _async_get_annual_bills(self) -> list[AnnualBillEntry]:
        try:
            data = await self._get(
                "relay/bills/summary",
                self._contract_params(onlyUnpay="N", f="annual"),
            )
        except KoreaGasAppApiError as err:
            _LOGGER.warning("Could not fetch annual bills: %s", err)
            return []

        if isinstance(data, list):
            rows = data
        elif isinstance(data, dict):
            rows = data.get("data") or data.get("list") or []
        else:
            rows = []

        entries = [
            AnnualBillEntry(
                request_ym=str(row["requestYm"]),
                usage_qty=_coerce_int(row.get("usageQty")),
                charge_amt_qty=_coerce_int(row.get("chargeAmtQty")),
            )
            for row in rows
            if isinstance(row, dict) and row.get("requestYm")
        ]
        entries.sort(key=lambda e: e.request_ym, reverse=True)
        return entries

    async def _async_get_indication(self) -> IndicationInfo:
        try:
            data = await self._get("relay/indications", self._contract_params())
        except KoreaGasAppApiError as err:
            _LOGGER.warning("Could not fetch indication info: %s", err)
            return IndicationInfo()

        if not isinstance(data, dict):
            return IndicationInfo()

        raw_available = data.get("selfInputAvailable")
        self_input_available: bool | None = None
        if raw_available is not None:
            self_input_available = str(raw_available).upper() in {"TRUE", "Y", "1"}

        return IndicationInfo(
            last_month_indicator=_coerce_int(data.get("lastMonthIndicatorQty")),
            self_input_available=self_input_available,
            period_start=data.get("periodStart"),
            period_end=data.get("periodEnd"),
            period_type=data.get("periodType"),
            request_ym=data.get("requestYm"),
        )

    async def _async_get_indication_history(self, limit: int = 6) -> list[IndicationHistoryEntry]:
        try:
            data = await self._get(
                "relay/indications/history",
                self._contract_params(limit=limit),
            )
        except KoreaGasAppApiError as err:
            _LOGGER.warning("Could not fetch indication history: %s", err)
            return []

        rows = data if isinstance(data, list) else []
        return [
            IndicationHistoryEntry(
                reading_date=str(row["gmtrJobYmd"]),
                request_ym=str(row.get("requestYm") or ""),
                indicator=_coerce_int(row.get("indiCompensThisMonthVc")),
                method=row.get("gmtrMethod"),
            )
            for row in rows
            if isinstance(row, dict) and row.get("gmtrJobYmd")
        ]

    # ── Auth / session methods ────────────────────────────────────────────

    async def async_request_sms(
        self,
        *,
        mobile_co: str,
        mobile_no: str,
        birthday: str,
        gender_code: str,
        name: str,
    ) -> SmsRequestResult:
        """Request a NICE SMS verification code."""
        response = await self._post_json(
            "extern/auth/nice/sms/request",
            {
                "mobileCo": mobile_co,
                "mobileNo": mobile_no,
                "birthday": birthday,
                "gender": gender_code,
                "name": name,
            },
            headers=self._anonymous_headers,
        )
        if not isinstance(response, dict):
            raise KoreaGasAppApiError("Unexpected SMS request response format")
        request_no = response.get("requestNo")
        response_uniq_id = response.get("responseUniqId")
        if not request_no or not response_uniq_id:
            raise KoreaGasAppApiError(
                response.get("responseMessage")
                or response.get("resultMessage")
                or "No SMS verification request ID returned"
            )
        return SmsRequestResult(request_no=str(request_no), response_uniq_id=str(response_uniq_id))

    async def async_confirm_sms(
        self,
        *,
        request_no: str,
        response_uniq_id: str,
        otp: str,
    ) -> SmsConfirmResult:
        """Confirm the NICE SMS verification code and obtain CI/DI."""
        response = await self._post_json(
            "extern/auth/nice/sms/confirm",
            {"requestNo": request_no, "responseUniqId": response_uniq_id, "otp": otp},
            headers=self._anonymous_headers,
        )
        if not isinstance(response, dict):
            raise KoreaGasAppApiError("Unexpected SMS confirm response format")
        ci = response.get("ci")
        di = response.get("di")
        if not ci or not di:
            raise KoreaGasAppAuthError(
                response.get("responseMessage") or "SMS verification failed"
            )
        return SmsConfirmResult(ci=str(ci), di=str(di))

    async def async_create_member(
        self,
        *,
        name: str,
        birth_date: str,
        mobile_no: str,
        gender: str,
        ci: str,
        di: str,
        adid: str,
        marketing_acceptance: str = "N",
    ) -> MemberLoginResult:
        """Create or re-register a Gas App member and obtain a session token."""
        response = await self._post_json(
            "members",
            {
                "gender": gender,
                "name": name,
                "birthDate": birth_date,
                "handphone": mobile_no,
                "ci": ci,
                "di": di,
                "marketingAcceptance": marketing_acceptance,
                "adid": adid,
                "nation": "N",
                "mid": None,
            },
            headers=self._anonymous_headers,
        )
        if not isinstance(response, dict):
            raise KoreaGasAppApiError("Unexpected member creation response format")
        member_no = response.get("member")
        auth_token = response.get("token")
        if not member_no or not auth_token:
            raise KoreaGasAppAuthError(
                response.get("message") or "No member number or token returned"
            )
        return MemberLoginResult(member_no=str(member_no), auth_token=str(auth_token))

    async def async_get_init(
        self,
        *,
        auth_token: str | None = None,
        member_no: str | None = None,
        company_code: str = "0",
    ) -> Any:
        """Fetch the app initialisation payload (contract list etc.)."""
        headers = self._headers_with(
            auth_token=auth_token or self._auth_token or "",
            member_no=member_no or self._member_no or "",
            company_code=company_code,
        )
        return await self._get("init", {}, headers=headers)

    async def async_submit_meter_reading(self, reading: int) -> MeterReadingSubmitResult:
        """Submit a self meter reading value to the Gas App API."""
        await self.validate()
        if not self._use_contract_num:
            raise KoreaGasAppApiError("Use contract number is required for submission")

        response = await self._post_json(
            "relay/indications/input",
            {
                "thisMonthIndicatorCustomer": str(reading),
                "useContractNum": self._use_contract_num,
                "customerNum": self._customer_no or "",
            },
        )
        if not isinstance(response, dict):
            raise KoreaGasAppApiError("Unexpected submission response format")

        result = MeterReadingSubmitResult(
            input_yn=response.get("inputYn"),
            error_code=response.get("errorCode"),
            return_message=response.get("returnMessage"),
            last_month_indicator=_coerce_int(response.get("lastMonthIndicator")),
            this_month_indicator=_coerce_int(response.get("thisMonthIndicator")),
            expectation_charge=_coerce_int(response.get("expectationCharge")),
            usage=_coerce_int(response.get("usage")),
        )
        if result.input_yn != "Y":
            raise KoreaGasAppApiError(
                result.return_message or result.error_code or "Gas App rejected the reading"
            )
        return result

    # ── HTTP transport ────────────────────────────────────────────────────

    def _contract_params(self, **extra: Any) -> dict[str, Any]:
        """Build base query params that identify the contract."""
        params: dict[str, Any] = {"customerNum": self._customer_no or ""}
        if self._use_contract_num:
            params["useContractNum"] = self._use_contract_num
        params.update(extra)
        return params

    async def _get(
        self,
        path: str,
        params: dict[str, Any],
        *,
        headers: dict[str, str] | None = None,
    ) -> Any:
        if self._session is None:
            raise KoreaGasAppEndpointUnknownError("HTTP session is not available")
        async with self._session.get(
            urljoin(self._base_url, path),
            params=params,
            headers=headers or self._headers,
        ) as response:
            if response.status == 401:
                raise KoreaGasAppAuthError("Session token is invalid or expired")
            if response.status >= 400:
                body = await response.text()
                raise KoreaGasAppApiError(
                    f"GET {path} failed with HTTP {response.status}: {body[:200]}"
                )
            return await response.json()

    async def _post_json(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        headers: dict[str, str] | None = None,
    ) -> Any:
        if self._session is None:
            raise KoreaGasAppEndpointUnknownError("HTTP session is not available")
        async with self._session.post(
            urljoin(self._base_url, path),
            json=payload,
            headers=headers or self._headers,
        ) as response:
            if response.status == 401:
                raise KoreaGasAppAuthError("Session token is invalid or expired")
            if response.status >= 400:
                body = await response.text()
                raise KoreaGasAppApiError(
                    f"POST {path} failed with HTTP {response.status}: {body[:200]}"
                )
            return await response.json()

    # ── Header builders ───────────────────────────────────────────────────

    @property
    def _headers(self) -> dict[str, str]:
        return self._headers_with(
            auth_token=self._auth_token or "",
            member_no=self._member_no or "",
            company_code=self._company_code or "",
        )

    @property
    def _anonymous_headers(self) -> dict[str, str]:
        """Headers for endpoints called before a member session exists."""
        return self._headers_with(auth_token="", member_no="", company_code="null")

    def _headers_with(
        self,
        *,
        auth_token: str,
        member_no: str,
        company_code: str,
    ) -> dict[str, str]:
        return {
            "Accept": "*/*",
            "User-Agent": self._user_agent,
            "X-VERSION": self._app_version,
            "X-PLATFORM": self._platform,
            "X-TOKEN": auth_token,
            "X-MEMBER": member_no,
            "X-COMPANY": company_code,
            "X-ADID": self._adid or "",
            "X-TID": self._tid or "",
            "X-WEBVERSION": DEFAULT_WEB_VERSION,
            "X-OS-VERSION": self._os_version or "",
            "X-DEVICE-NAME": self._device_name or "",
            "X-DEVID": self._device_id or "",
        }


# ── Module-level value parsers ────────────────────────────────────────────────
# Kept as free functions (not static methods) so they can be reused by other
# modules without importing the full client class.

def _parse_krw(value: str) -> int | None:
    """Parse a Korean-won string such as '17,480 원' or '-840 원' to int."""
    return _parse_numeric_int(value, strip_suffix="원")


def _parse_numeric_int(value: str, strip_suffix: str = "") -> int | None:
    """Strip an optional suffix, remove commas, and parse as int."""
    cleaned = value.replace(strip_suffix, "").replace(",", "").strip()
    try:
        return int(float(cleaned))
    except (ValueError, TypeError):
        return None


def _parse_numeric_float(value: str, strip_suffix: str = "") -> float | None:
    """Strip an optional suffix, remove commas, and parse as float."""
    cleaned = value.replace(strip_suffix, "").replace(",", "").strip()
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return None


def _coerce_int(value: Any) -> int | None:
    """Coerce an API field that may be int, float-string, or None to int."""
    if value is None:
        return None
    return _parse_numeric_int(str(value))

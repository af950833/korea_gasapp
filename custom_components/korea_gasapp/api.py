"""Client for the Korea Gas App backend."""

from __future__ import annotations

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


class KoreaGasAppApiError(Exception):
    """Base API error."""


class KoreaGasAppAuthError(KoreaGasAppApiError):
    """Authentication failed or expired."""


class KoreaGasAppEndpointUnknownError(KoreaGasAppApiError):
    """The app API endpoint has not been discovered yet."""


@dataclass(slots=True)
class BillDetail:
    """Parsed key-value pairs from the bill detail areas."""

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
    """Current month bill data from relay/bills/month."""

    charge_krw: int | None = None
    title: str | None = None
    status: str | None = None
    payable: bool | None = None
    detail: BillDetail = field(default_factory=BillDetail)


@dataclass(slots=True)
class AnnualBillEntry:
    """One row from the annual bill summary."""

    request_ym: str
    usage_qty: int | None = None
    charge_amt_qty: int | None = None


@dataclass(slots=True)
class IndicationHistoryEntry:
    """One row from the indication history."""

    reading_date: str
    request_ym: str
    indicator: int | None = None
    method: str | None = None


@dataclass(slots=True)
class IndicationInfo:
    """Current indication status from relay/indications."""

    last_month_indicator: int | None = None
    self_input_available: bool | None = None
    # True when the account has signed up for self-reading service.
    # Derived from history method labels or selfInputAvailable flag.
    self_reading_registered: bool = False
    period_start: str | None = None
    period_end: str | None = None
    period_type: str | None = None
    request_ym: str | None = None


@dataclass(slots=True)
class GasUsageSnapshot:
    """All data polled in one coordinator refresh."""

    customer_no: str
    use_contract_num: str
    current_bill: CurrentBillSnapshot = field(default_factory=CurrentBillSnapshot)
    annual_bills: list[AnnualBillEntry] = field(default_factory=list)
    indication: IndicationInfo = field(default_factory=IndicationInfo)
    indication_history: list[IndicationHistoryEntry] = field(default_factory=list)
    # Convenience aliases used by __init__.py
    self_input_available: bool | None = None
    last_meter_reading_m3: float | None = None


@dataclass(slots=True)
class MeterReadingSubmitResult:
    """Result returned by the self-reading submission API."""

    input_yn: str | None = None
    error_code: str | None = None
    return_message: str | None = None
    last_month_indicator: int | None = None
    this_month_indicator: int | None = None
    expectation_charge: int | None = None
    usage: int | None = None


@dataclass(slots=True)
class SmsRequestResult:
    """Result returned after requesting a NICE SMS verification code."""

    request_no: str
    response_uniq_id: str


@dataclass(slots=True)
class SmsConfirmResult:
    """Result returned after confirming a NICE SMS verification code."""

    ci: str
    di: str


@dataclass(slots=True)
class MemberLoginResult:
    """Result returned after creating or re-registering a Gas App member."""

    member_no: str
    auth_token: str


class KoreaGasAppClient:
    """Async HTTP client for the Korea Gas App API."""

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

    async def validate(self) -> None:
        if not self._customer_no and not self._use_contract_num:
            raise KoreaGasAppAuthError("Customer number or use contract number is required")
        if not self._auth_token or not self._member_no or not self._company_code:
            raise KoreaGasAppAuthError(
                "X-TOKEN, X-MEMBER, and X-COMPANY values from the app session are required"
            )

    # ------------------------------------------------------------------ #
    # Public data methods                                                   #
    # ------------------------------------------------------------------ #

    async def async_get_usage(self) -> GasUsageSnapshot:
        """Fetch the full usage snapshot."""
        await self.validate()

        current_bill = await self._async_get_current_bill()
        annual_bills = await self._async_get_annual_bills()
        indication = await self._async_get_indication()
        history = await self._async_get_indication_history()

        # Determine self-reading registration.
        # If any history entry has method "자가검침", the account is registered.
        # Also trust selfInputAvailable=True from the API (window is open → registered).
        history_registered = any(
            (item.method or "").strip() == "자가검침" for item in history
        )
        indication.self_reading_registered = (
            history_registered or indication.self_input_available is True
        )

        last_reading: float | None = None
        if indication.last_month_indicator is not None:
            last_reading = float(indication.last_month_indicator)

        return GasUsageSnapshot(
            customer_no=self._customer_no,
            use_contract_num=self._use_contract_num or "",
            current_bill=current_bill,
            annual_bills=annual_bills,
            indication=indication,
            indication_history=history,
            self_input_available=indication.self_input_available,
            last_meter_reading_m3=last_reading,
        )

    async def _async_get_current_bill(self) -> CurrentBillSnapshot:
        try:
            data = await self._get(
                "relay/bills/month",
                self._contract_params(history="Y", deadlineFlag="", requestYm=""),
            )
        except KoreaGasAppApiError:
            return CurrentBillSnapshot()

        if not isinstance(data, dict):
            return CurrentBillSnapshot()

        charge = self._parse_krw(data.get("amount", ""))
        detail = BillDetail()

        for area in (
            data.get("areaEtc") or [],
            data.get("areaPayment") or [],
            data.get("areaUnpayment") or [],
            data.get("areaUsage") or [],
        ):
            for item in area:
                if not isinstance(item, dict):
                    continue
                k = item.get("key", "")
                v = item.get("value", "")
                if k == "기본요금":
                    detail.basic_charge = self._parse_krw(v)
                elif k == "사용요금":
                    detail.usage_charge = self._parse_krw(v)
                elif k == "부가세":
                    detail.vat = self._parse_krw(v)
                elif k == "할인금액":
                    detail.discount = self._parse_krw(v)
                elif k == "절사금액":
                    detail.truncation = self._parse_krw(v)
                elif k == "미납 소계":
                    detail.unpaid = self._parse_krw(v)
                elif k == "사용 기간":
                    detail.usage_period = v
                elif k == "납부 마감일":
                    detail.due_date = v
                elif k == "당월지침":
                    detail.this_month_indicator = self._parse_m3_int(v)
                elif k == "전월지침":
                    detail.last_month_indicator = self._parse_m3_int(v)
                elif k == "당월사용량":
                    detail.monthly_usage = self._parse_m3_int(v)
                elif k == "보정 계수":
                    detail.correction_factor = self._try_float(v)
                elif k == "보정량":
                    detail.correction_usage = self._parse_m3_float(v)
                elif k == "평균열량":
                    detail.avg_calorific = self._try_float(v.replace("MJ/m³", "").strip())
                elif k == "사용열량":
                    detail.used_calorific = self._try_float(v.replace("MJ", "").strip())
                elif k == "계량기 번호":
                    detail.meter_id = v
                elif k == "검침일":
                    detail.reading_day = v
                elif k == "검침방법":
                    detail.reading_method = v
                elif k == "전월 사용량":
                    detail.prev_month_usage = v
                elif k == "전년 동월 사용량":
                    detail.prev_year_usage = v
                elif k == "할인종류":
                    detail.discount_type = v

        return CurrentBillSnapshot(
            charge_krw=charge,
            title=data.get("title"),
            status=data.get("status"),
            payable=data.get("payable") == "Y",
            detail=detail,
        )

    async def _async_get_annual_bills(self) -> list[AnnualBillEntry]:
        try:
            data = await self._get(
                "relay/bills/summary",
                self._contract_params(onlyUnpay="N", f="annual"),
            )
        except KoreaGasAppApiError:
            return []

        rows: list[Any] = []
        if isinstance(data, list):
            rows = data
        elif isinstance(data, dict):
            rows = data.get("data") or data.get("list") or []

        result: list[AnnualBillEntry] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            ym = row.get("requestYm")
            if not ym:
                continue
            result.append(
                AnnualBillEntry(
                    request_ym=str(ym),
                    usage_qty=self._coerce_int(row.get("usageQty")),
                    charge_amt_qty=self._coerce_int(row.get("chargeAmtQty")),
                )
            )

        result.sort(key=lambda e: e.request_ym, reverse=True)
        return result

    async def _async_get_indication(self) -> IndicationInfo:
        try:
            data = await self._get("relay/indications", self._contract_params())
        except KoreaGasAppApiError:
            return IndicationInfo()

        if not isinstance(data, dict):
            return IndicationInfo()

        available_raw = data.get("selfInputAvailable")
        available: bool | None = None
        if available_raw is not None:
            available = str(available_raw).upper() in {"TRUE", "Y", "1"}

        return IndicationInfo(
            last_month_indicator=self._coerce_int(data.get("lastMonthIndicatorQty")),
            self_input_available=available,
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
        except KoreaGasAppApiError:
            return []

        rows: list[Any] = data if isinstance(data, list) else []
        result: list[IndicationHistoryEntry] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            date_val = row.get("gmtrJobYmd")
            ym = row.get("requestYm")
            if not date_val:
                continue
            result.append(
                IndicationHistoryEntry(
                    reading_date=str(date_val),
                    request_ym=str(ym) if ym else "",
                    indicator=self._coerce_int(row.get("indiCompensThisMonthVc")),
                    method=row.get("gmtrMethod"),
                )
            )
        return result

    # ------------------------------------------------------------------ #
    # Auth / session methods                                               #
    # ------------------------------------------------------------------ #

    async def async_request_sms(
        self,
        *,
        mobile_co: str,
        mobile_no: str,
        birthday: str,
        gender_code: str,
        name: str,
    ) -> SmsRequestResult:
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
            raise KoreaGasAppApiError("Unexpected Gas App SMS request response")
        request_no = response.get("requestNo")
        response_uniq_id = response.get("responseUniqId")
        if not request_no or not response_uniq_id:
            raise KoreaGasAppApiError(
                response.get("responseMessage")
                or response.get("resultMessage")
                or "Gas App did not return an SMS verification request id"
            )
        return SmsRequestResult(request_no=str(request_no), response_uniq_id=str(response_uniq_id))

    async def async_confirm_sms(
        self,
        *,
        request_no: str,
        response_uniq_id: str,
        otp: str,
    ) -> SmsConfirmResult:
        response = await self._post_json(
            "extern/auth/nice/sms/confirm",
            {
                "requestNo": request_no,
                "responseUniqId": response_uniq_id,
                "otp": otp,
            },
            headers=self._anonymous_headers,
        )
        if not isinstance(response, dict):
            raise KoreaGasAppApiError("Unexpected Gas App SMS confirm response")
        ci = response.get("ci")
        di = response.get("di")
        if not ci or not di:
            raise KoreaGasAppAuthError(
                response.get("responseMessage")
                or response.get("resultMessage")
                or "Gas App SMS verification failed"
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
            raise KoreaGasAppApiError("Unexpected Gas App member response")
        member_no = response.get("member")
        auth_token = response.get("token")
        if not member_no or not auth_token:
            raise KoreaGasAppAuthError(
                response.get("message")
                or "Gas App did not return a member number and token"
            )
        return MemberLoginResult(member_no=str(member_no), auth_token=str(auth_token))

    async def async_get_init(
        self,
        *,
        auth_token: str | None = None,
        member_no: str | None = None,
        company_code: str = "0",
    ) -> Any:
        headers = self._headers_with(
            auth_token=auth_token or self._auth_token or "",
            member_no=member_no or self._member_no or "",
            company_code=company_code,
        )
        return await self._get("init", {}, headers=headers)

    async def async_submit_meter_reading(self, reading: int) -> MeterReadingSubmitResult:
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
            raise KoreaGasAppApiError("Unexpected Gas App submission response")

        result = MeterReadingSubmitResult(
            input_yn=response.get("inputYn"),
            error_code=response.get("errorCode"),
            return_message=response.get("returnMessage"),
            last_month_indicator=self._coerce_int(response.get("lastMonthIndicator")),
            this_month_indicator=self._coerce_int(response.get("thisMonthIndicator")),
            expectation_charge=self._coerce_int(response.get("expectationCharge")),
            usage=self._coerce_int(response.get("usage")),
        )
        if result.input_yn != "Y":
            raise KoreaGasAppApiError(
                result.return_message
                or result.error_code
                or "Gas App rejected the meter reading"
            )
        return result

    # ------------------------------------------------------------------ #
    # HTTP helpers                                                          #
    # ------------------------------------------------------------------ #

    def _contract_params(self, **extra: Any) -> dict[str, Any]:
        params: dict[str, Any] = {"customerNum": self._customer_no or ""}
        if self._use_contract_num:
            params["useContractNum"] = self._use_contract_num
        params.update(extra)
        return params

    async def _get(self, path: str, params: dict[str, Any], *, headers: dict[str, str] | None = None) -> Any:
        if self._session is None:
            raise KoreaGasAppEndpointUnknownError("HTTP session is not available")
        async with self._session.get(
            urljoin(self._base_url, path),
            params=params,
            headers=headers or self._headers,
        ) as response:
            if response.status == 401:
                raise KoreaGasAppAuthError("Gas App session token is invalid or expired")
            if response.status >= 400:
                body = await response.text()
                raise KoreaGasAppApiError(f"Gas App API request failed: {response.status} {body[:200]}")
            return await response.json()

    async def _post_json(self, path: str, payload: dict[str, Any], *, headers: dict[str, str] | None = None) -> Any:
        if self._session is None:
            raise KoreaGasAppEndpointUnknownError("HTTP session is not available")
        async with self._session.post(
            urljoin(self._base_url, path),
            json=payload,
            headers=headers or self._headers,
        ) as response:
            if response.status == 401:
                raise KoreaGasAppAuthError("Gas App session token is invalid or expired")
            if response.status >= 400:
                body = await response.text()
                raise KoreaGasAppApiError(f"Gas App API request failed: {response.status} {body[:200]}")
            return await response.json()

    @property
    def _headers(self) -> dict[str, str]:
        return self._headers_with(
            auth_token=self._auth_token or "",
            member_no=self._member_no or "",
            company_code=self._company_code or "",
        )

    @property
    def _anonymous_headers(self) -> dict[str, str]:
        return self._headers_with(auth_token="", member_no="", company_code="null")

    def _headers_with(self, *, auth_token: str, member_no: str, company_code: str) -> dict[str, str]:
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

    # ------------------------------------------------------------------ #
    # Value parsing helpers                                                 #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _parse_krw(value: str) -> int | None:
        if not value:
            return None
        try:
            return int(float(value.replace(",", "").replace("원", "").strip()))
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _parse_m3_int(value: str) -> int | None:
        try:
            return int(float(value.replace("m³", "").replace(",", "").strip()))
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _parse_m3_float(value: str) -> float | None:
        try:
            return float(value.replace("m³", "").replace(",", "").strip())
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _try_float(value: Any) -> float | None:
        try:
            return float(str(value).replace(",", "").strip())
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _coerce_int(value: Any) -> int | None:
        if value is None:
            return None
        if isinstance(value, str):
            value = value.replace(",", "").strip()
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None

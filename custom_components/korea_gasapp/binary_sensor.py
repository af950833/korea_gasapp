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
    CONF_ACCOUNT_ID, CONF_ADID, CONF_APP_VERSION, CONF_AUTH_TOKEN, CONF_COMPANY_CODE,
    CONF_CUSTOMER_NO, CONF_DEVICE_ID, CONF_DEVICE_NAME, CONF_MEMBER_NO, CONF_OS_VERSION,
    CONF_PLATFORM, CONF_TID, CONF_USER_AGENT, CONF_USE_CONTRACT_NUM,
    DEFAULT_API_BASE_URL, DEFAULT_APP_PLATFORM, DEFAULT_APP_VERSION,
    DEFAULT_USER_AGENT, DEFAULT_WEB_VERSION,
)


class KoreaGasAppApiError(Exception):
    """Base API error."""

class KoreaGasAppAuthError(KoreaGasAppApiError):
    """Authentication failed or expired."""

class KoreaGasAppEndpointUnknownError(KoreaGasAppApiError):
    """The app API endpoint has not been discovered yet."""


@dataclass(slots=True)
class BillDetail:
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
    charge_krw: int | None = None
    title: str | None = None
    status: str | None = None
    payable: bool | None = None
    detail: BillDetail = field(default_factory=BillDetail)


@dataclass(slots=True)
class AnnualBillEntry:
    request_ym: str
    usage_qty: int | None = None
    charge_amt_qty: int | None = None


@dataclass(slots=True)
class IndicationHistoryEntry:
    reading_date: str
    request_ym: str
    indicator: int | None = None
    method: str | None = None


@dataclass(slots=True)
class IndicationInfo:
    last_month_indicator: int | None = None
    self_input_available: bool | None = None
    self_reading_registered: bool = False
    period_start: str | None = None
    period_end: str | None = None
    period_type: str | None = None
    request_ym: str | None = None


@dataclass(slots=True)
class GasUsageSnapshot:
    customer_no: str
    use_contract_num: str
    current_bill: CurrentBillSnapshot = field(default_factory=CurrentBillSnapshot)
    annual_bills: list[AnnualBillEntry] = field(default_factory=list)
    indication: IndicationInfo = field(default_factory=IndicationInfo)
    indication_history: list[IndicationHistoryEntry] = field(default_factory=list)
    self_input_available: bool | None = None
    last_meter_reading_m3: float | None = None


@dataclass(slots=True)
class MeterReadingSubmitResult:
    input_yn: str | None = None
    error_code: str | None = None
    return_message: str | None = None
    last_month_indicator: int | None = None
    this_month_indicator: int | None = None
    expectation_charge: int | None = None
    usage: int | None = None


@dataclass(slots=True)
class SmsRequestResult:
    request_no: str
    response_uniq_id: str


@dataclass(slots=True)
class SmsConfirmResult:
    ci: str
    di: str


@dataclass(slots=True)
class MemberLoginResult:
    member_no: str
    auth_token: str


class KoreaGasAppClient:
    """Async HTTP client for the Korea Gas App API."""

    def __init__(self, session, *, account_id, customer_no, auth_token=None, member_no=None,
                 company_code=None, use_contract_num=None, adid=None, tid=None,
                 app_version=None, platform=None, os_version=None, device_name=None,
                 device_id=None, user_agent=None, base_url=DEFAULT_API_BASE_URL):
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
    def from_config_entry(cls, hass: HomeAssistant, entry: ConfigEntry) -> "KoreaGasAppClient":
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
            raise KoreaGasAppAuthError("X-TOKEN, X-MEMBER, and X-COMPANY values are required")

    async def async_get_usage(self) -> GasUsageSnapshot:
        await self.validate()
        current_bill = await self._async_get_current_bill()
        annual_bills = await self._async_get_annual_bills()
        indication = await self._async_get_indication()
        history = await self._async_get_indication_history()

        history_registered = any((item.method or "").strip() == "자가검침" for item in history)
        indication.self_reading_registered = history_registered or indication.self_input_available is True

        last_reading = float(indication.last_month_indicator) if indication.last_month_indicator is not None else None

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
            data = await self._get("relay/bills/month", self._contract_params(history="Y", deadlineFlag="", requestYm=""))
        except KoreaGasAppApiError:
            return CurrentBillSnapshot()
        if not isinstance(data, dict):
            return CurrentBillSnapshot()

        charge = self._parse_krw(data.get("amount", ""))
        detail = BillDetail()
        _KEY_MAP = {
            "기본요금": ("basic_charge", "krw"), "사용요금": ("usage_charge", "krw"),
            "부가세": ("vat", "krw"), "할인금액": ("discount", "krw"),
            "절사금액": ("truncation", "krw"), "미납 소계": ("unpaid", "krw"),
            "사용 기간": ("usage_period", "str"), "납부 마감일": ("due_date", "str"),
            "당월지침": ("this_month_indicator", "m3i"), "전월지침": ("last_month_indicator", "m3i"),
            "당월사용량": ("monthly_usage", "m3i"), "보정 계수": ("correction_factor", "float"),
            "보정량": ("correction_usage", "m3f"), "평균열량": ("avg_calorific", "mj_m3"),
            "사용열량": ("used_calorific", "mj"), "계량기 번호": ("meter_id", "str"),
            "검침일": ("reading_day", "str"), "검침방법": ("reading_method", "str"),
            "전월 사용량": ("prev_month_usage", "str"), "전년 동월 사용량": ("prev_year_usage", "str"),
            "할인종류": ("discount_type", "str"),
        }
        for area in (data.get("areaEtc") or [], data.get("areaPayment") or [],
                     data.get("areaUnpayment") or [], data.get("areaUsage") or []):
            for item in area:
                if not isinstance(item, dict):
                    continue
                k, v = item.get("key", ""), item.get("value", "")
                if k not in _KEY_MAP:
                    continue
                attr, typ = _KEY_MAP[k]
                if typ == "krw":
                    setattr(detail, attr, self._parse_krw(v))
                elif typ == "str":
                    setattr(detail, attr, v)
                elif typ == "m3i":
                    setattr(detail, attr, self._parse_m3_int(v))
                elif typ == "m3f":
                    setattr(detail, attr, self._parse_m3_float(v))
                elif typ == "float":
                    setattr(detail, attr, self._try_float(v))
                elif typ == "mj_m3":
                    setattr(detail, attr, self._try_float(v.replace("MJ/m³", "").strip()))
                elif typ == "mj":
                    setattr(detail, attr, self._try_float(v.replace("MJ", "").strip()))

        return CurrentBillSnapshot(charge_krw=charge, title=data.get("title"),
                                   status=data.get("status"), payable=data.get("payable") == "Y", detail=detail)

    async def _async_get_annual_bills(self) -> list[AnnualBillEntry]:
        try:
            data = await self._get("relay/bills/summary", self._contract_params(onlyUnpay="N", f="annual"))
        except KoreaGasAppApiError:
            return []
        rows = data if isinstance(data, list) else (data.get("data") or data.get("list") or [] if isinstance(data, dict) else [])
        result = [AnnualBillEntry(request_ym=str(r["requestYm"]),
                                  usage_qty=self._coerce_int(r.get("usageQty")),
                                  charge_amt_qty=self._coerce_int(r.get("chargeAmtQty")))
                  for r in rows if isinstance(r, dict) and r.get("requestYm")]
        result.sort(key=lambda e: e.request_ym, reverse=True)
        return result

    async def _async_get_indication(self) -> IndicationInfo:
        try:
            data = await self._get("relay/indications", self._contract_params())
        except KoreaGasAppApiError:
            return IndicationInfo()
        if not isinstance(data, dict):
            return IndicationInfo()
        raw = data.get("selfInputAvailable")
        available = str(raw).upper() in {"TRUE", "Y", "1"} if raw is not None else None
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
            data = await self._get("relay/indications/history", self._contract_params(limit=limit))
        except KoreaGasAppApiError:
            return []
        rows = data if isinstance(data, list) else []
        return [IndicationHistoryEntry(reading_date=str(r["gmtrJobYmd"]),
                                       request_ym=str(r.get("requestYm") or ""),
                                       indicator=self._coerce_int(r.get("indiCompensThisMonthVc")),
                                       method=r.get("gmtrMethod"))
                for r in rows if isinstance(r, dict) and r.get("gmtrJobYmd")]

    async def async_request_sms(self, *, mobile_co, mobile_no, birthday, gender_code, name) -> SmsRequestResult:
        response = await self._post_json("extern/auth/nice/sms/request",
            {"mobileCo": mobile_co, "mobileNo": mobile_no, "birthday": birthday, "gender": gender_code, "name": name},
            headers=self._anonymous_headers)
        if not isinstance(response, dict):
            raise KoreaGasAppApiError("Unexpected SMS request response")
        rn, ruid = response.get("requestNo"), response.get("responseUniqId")
        if not rn or not ruid:
            raise KoreaGasAppApiError(response.get("responseMessage") or response.get("resultMessage") or "No SMS request id")
        return SmsRequestResult(request_no=str(rn), response_uniq_id=str(ruid))

    async def async_confirm_sms(self, *, request_no, response_uniq_id, otp) -> SmsConfirmResult:
        response = await self._post_json("extern/auth/nice/sms/confirm",
            {"requestNo": request_no, "responseUniqId": response_uniq_id, "otp": otp},
            headers=self._anonymous_headers)
        if not isinstance(response, dict):
            raise KoreaGasAppApiError("Unexpected SMS confirm response")
        ci, di = response.get("ci"), response.get("di")
        if not ci or not di:
            raise KoreaGasAppAuthError(response.get("responseMessage") or "SMS verification failed")
        return SmsConfirmResult(ci=str(ci), di=str(di))

    async def async_create_member(self, *, name, birth_date, mobile_no, gender, ci, di, adid, marketing_acceptance="N") -> MemberLoginResult:
        response = await self._post_json("members",
            {"gender": gender, "name": name, "birthDate": birth_date, "handphone": mobile_no,
             "ci": ci, "di": di, "marketingAcceptance": marketing_acceptance, "adid": adid, "nation": "N", "mid": None},
            headers=self._anonymous_headers)
        if not isinstance(response, dict):
            raise KoreaGasAppApiError("Unexpected member response")
        mn, at = response.get("member"), response.get("token")
        if not mn or not at:
            raise KoreaGasAppAuthError(response.get("message") or "No member number and token")
        return MemberLoginResult(member_no=str(mn), auth_token=str(at))

    async def async_get_init(self, *, auth_token=None, member_no=None, company_code="0") -> Any:
        headers = self._headers_with(auth_token=auth_token or self._auth_token or "",
                                     member_no=member_no or self._member_no or "",
                                     company_code=company_code)
        return await self._get("init", {}, headers=headers)

    async def async_submit_meter_reading(self, reading: int) -> MeterReadingSubmitResult:
        await self.validate()
        if not self._use_contract_num:
            raise KoreaGasAppApiError("Use contract number is required")
        response = await self._post_json("relay/indications/input",
            {"thisMonthIndicatorCustomer": str(reading), "useContractNum": self._use_contract_num,
             "customerNum": self._customer_no or ""})
        if not isinstance(response, dict):
            raise KoreaGasAppApiError("Unexpected submission response")
        result = MeterReadingSubmitResult(
            input_yn=response.get("inputYn"), error_code=response.get("errorCode"),
            return_message=response.get("returnMessage"),
            last_month_indicator=self._coerce_int(response.get("lastMonthIndicator")),
            this_month_indicator=self._coerce_int(response.get("thisMonthIndicator")),
            expectation_charge=self._coerce_int(response.get("expectationCharge")),
            usage=self._coerce_int(response.get("usage")),
        )
        if result.input_yn != "Y":
            raise KoreaGasAppApiError(result.return_message or result.error_code or "Reading rejected")
        return result

    def _contract_params(self, **extra) -> dict:
        params = {"customerNum": self._customer_no or ""}
        if self._use_contract_num:
            params["useContractNum"] = self._use_contract_num
        params.update(extra)
        return params

    async def _get(self, path, params, *, headers=None) -> Any:
        if self._session is None:
            raise KoreaGasAppEndpointUnknownError("HTTP session is not available")
        async with self._session.get(urljoin(self._base_url, path), params=params, headers=headers or self._headers) as r:
            if r.status == 401:
                raise KoreaGasAppAuthError("Session token is invalid or expired")
            if r.status >= 400:
                raise KoreaGasAppApiError(f"API request failed: {r.status} {(await r.text())[:200]}")
            return await r.json()

    async def _post_json(self, path, payload, *, headers=None) -> Any:
        if self._session is None:
            raise KoreaGasAppEndpointUnknownError("HTTP session is not available")
        async with self._session.post(urljoin(self._base_url, path), json=payload, headers=headers or self._headers) as r:
            if r.status == 401:
                raise KoreaGasAppAuthError("Session token is invalid or expired")
            if r.status >= 400:
                raise KoreaGasAppApiError(f"API request failed: {r.status} {(await r.text())[:200]}")
            return await r.json()

    @property
    def _headers(self) -> dict:
        return self._headers_with(auth_token=self._auth_token or "", member_no=self._member_no or "", company_code=self._company_code or "")

    @property
    def _anonymous_headers(self) -> dict:
        return self._headers_with(auth_token="", member_no="", company_code="null")

    def _headers_with(self, *, auth_token, member_no, company_code) -> dict:
        return {
            "Accept": "*/*", "User-Agent": self._user_agent,
            "X-VERSION": self._app_version, "X-PLATFORM": self._platform,
            "X-TOKEN": auth_token, "X-MEMBER": member_no, "X-COMPANY": company_code,
            "X-ADID": self._adid or "", "X-TID": self._tid or "",
            "X-WEBVERSION": DEFAULT_WEB_VERSION, "X-OS-VERSION": self._os_version or "",
            "X-DEVICE-NAME": self._device_name or "", "X-DEVID": self._device_id or "",
        }

    @staticmethod
    def _parse_krw(value) -> int | None:
        try:
            return int(float(str(value).replace(",", "").replace("원", "").strip()))
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _parse_m3_int(value) -> int | None:
        try:
            return int(float(str(value).replace("m³", "").replace(",", "").strip()))
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _parse_m3_float(value) -> float | None:
        try:
            return float(str(value).replace("m³", "").replace(",", "").strip())
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _try_float(value) -> float | None:
        try:
            return float(str(value).replace(",", "").strip())
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _coerce_int(value) -> int | None:
        if value is None:
            return None
        try:
            return int(float(str(value).replace(",", "").strip()))
        except (TypeError, ValueError):
            return None

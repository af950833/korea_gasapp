"""Client for the Korea Gas App backend."""

from __future__ import annotations

from dataclasses import dataclass
import logging
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
    CONF_PUSH_TOKEN,
    CONF_TID,
    CONF_USER_AGENT,
    CONF_USE_CONTRACT_NUM,
    DEFAULT_API_BASE_URL,
    DEFAULT_APP_PLATFORM,
    DEFAULT_APP_VERSION,
    DEFAULT_IOS_APP_VERSION,
    DEFAULT_IOS_DEVICE_NAME,
    DEFAULT_IOS_OS_VERSION,
    DEFAULT_IOS_PLATFORM,
    DEFAULT_IOS_USER_AGENT,
    DEFAULT_IOS_WEBVIEW_USER_AGENT,
    DEFAULT_USER_AGENT,
    DEFAULT_WEB_VERSION,
)

_LOGGER = logging.getLogger(__name__)


class KoreaGasAppApiError(Exception):
    """Base API error."""


class KoreaGasAppAuthError(KoreaGasAppApiError):
    """Authentication failed or expired."""


class KoreaGasAppEndpointUnknownError(KoreaGasAppApiError):
    """The app API endpoint has not been discovered yet."""


@dataclass(slots=True)
class GasUsageSnapshot:
    """Latest gas usage and billing values."""

    customer_no: str
    use_contract_num: str
    latest_bill_month: str | None = None
    latest_bill_usage_m3: float | None = None
    latest_bill_charge_krw: int | None = None
    latest_indication_date: str | None = None
    last_meter_reading_m3: float | None = None
    self_input_available: bool | None = None


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
    """Small async client boundary for the eventual Gas App API."""

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
        push_token: str | None = None,
        base_url: str = DEFAULT_API_BASE_URL,
    ) -> None:
        """Initialize the client."""
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
        self._push_token = push_token
        self._base_url = base_url
        self._normalize_ios_profile()

    @classmethod
    def from_config_entry(
        cls,
        hass: HomeAssistant,
        entry: ConfigEntry,
    ) -> KoreaGasAppClient:
        """Create a client from a Home Assistant config entry."""
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
            push_token=entry.data.get(CONF_PUSH_TOKEN),
        )

    def _normalize_ios_profile(self) -> None:
        """Use the iOS webview profile for regular API requests."""
        if str(self._platform).upper() != DEFAULT_IOS_PLATFORM:
            return
        if not self._auth_token and not self._member_no:
            return

        if not self._app_version or self._app_version == DEFAULT_APP_VERSION:
            self._app_version = DEFAULT_IOS_APP_VERSION
        if (
            not self._user_agent
            or self._user_agent.startswith("WunderFlo Appstore/")
            or self._user_agent == DEFAULT_USER_AGENT
        ):
            self._user_agent = DEFAULT_IOS_WEBVIEW_USER_AGENT
        self._os_version = None
        self._device_name = None
        self._device_id = None

    async def validate(self) -> None:
        """Validate credentials.

        This becomes a real lightweight request once the mobile/webview
        endpoint and auth contract are known.
        """
        if not self._customer_no and not self._use_contract_num:
            raise KoreaGasAppAuthError(
                "Customer number or use contract number is required"
            )
        if not self._auth_token or not self._member_no or not self._company_code:
            raise KoreaGasAppAuthError(
                "X-TOKEN, X-MEMBER, and X-COMPANY values from the app session are required"
            )

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
            raise KoreaGasAppApiError("Unexpected Gas App SMS request response")
        request_no = response.get("requestNo")
        response_uniq_id = response.get("responseUniqId")
        if not request_no or not response_uniq_id:
            raise KoreaGasAppApiError(
                response.get("responseMessage")
                or response.get("resultMessage")
                or "Gas App did not return an SMS verification request id"
            )
        return SmsRequestResult(
            request_no=str(request_no),
            response_uniq_id=str(response_uniq_id),
        )

    async def async_confirm_sms(
        self,
        *,
        request_no: str,
        response_uniq_id: str,
        otp: str,
    ) -> SmsConfirmResult:
        """Confirm a NICE SMS verification code."""
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
        """Create or re-register a Gas App member session."""
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
        return MemberLoginResult(
            member_no=str(member_no),
            auth_token=str(auth_token),
        )

    async def async_get_init(
        self,
        *,
        auth_token: str | None = None,
        member_no: str | None = None,
        company_code: str = "0",
    ) -> Any:
        """Fetch the app initialization payload."""
        headers = self._headers_with(
            auth_token=auth_token or self._auth_token or "",
            member_no=member_no or self._member_no or "",
            company_code=company_code,
        )
        return await self._get("init", {}, headers=headers)

    async def async_refresh_session(self) -> None:
        """Register the current device session like the native app does."""
        await self.validate()
        if not self._adid and not self._device_id:
            _LOGGER.debug("Skipping Gas App session refresh: no device id is saved")
            return

        device_id = self._adid or self._device_id or ""
        payload: dict[str, Any] = {
            "osVersion": DEFAULT_IOS_OS_VERSION,
            "adid": device_id,
            "deviceName": DEFAULT_IOS_DEVICE_NAME,
        }
        if self._push_token:
            payload["pushToken"] = self._push_token

        headers = self._native_ios_headers(company_code="0", device_id=device_id)
        _LOGGER.debug(
            "Refreshing Gas App device session: device_name=%s os_version=%s "
            "has_push_token=%s",
            DEFAULT_IOS_DEVICE_NAME,
            DEFAULT_IOS_OS_VERSION,
            bool(self._push_token),
        )
        await self._put_json("sessions", payload, headers=headers)
        _LOGGER.debug("Gas App device session refresh succeeded")

    async def async_get_usage(self) -> GasUsageSnapshot:
        """Fetch the latest usage snapshot."""
        await self.validate()
        try:
            await self.async_refresh_session()
        except KoreaGasAppAuthError:
            raise
        except KoreaGasAppApiError as err:
            _LOGGER.debug("Could not refresh Gas App device session: %s", err)

        home = await self._get(
            "home",
            self._contract_params(amiYn="N"),
        )
        meter = await self._try_get("meters", self._contract_params())
        unpaid = await self._try_get_bill_summary("unpay", only_unpay="Y")
        paid = await self._try_get_bill_summary("pay", only_unpay="N")

        home_bill = self._home_bill(home)
        indication = self._home_indication(home)
        bill_history = self._home_bill_history(home)
        current_bill = home_bill or self._first_item(unpaid) or self._first_item(paid)

        latest_bill_usage = self._first_float(
            home_bill,
            bill_history,
            meter,
            current_bill,
            keys=(
                "useQty",
                "usageQty",
                "meterUsageQty",
                "gasUseQty",
                "replaceUsageQty",
                "currentUsageQty",
            ),
        )
        latest_bill_charge = self._first_int(
            current_bill,
            keys=(
                "chargeAmtQty",
                "title2",
                "chargeAmt",
                "billingCharge",
                "billAmt",
                "requestAmt",
                "payAmt",
            ),
        )

        return GasUsageSnapshot(
            customer_no=self._customer_no,
            use_contract_num=self._use_contract_num or "",
            latest_bill_month=self._first_str(
                current_bill,
                bill_history,
                keys=("requestYm", "requestMonth", "billYm"),
            ),
            latest_bill_usage_m3=latest_bill_usage,
            latest_bill_charge_krw=latest_bill_charge,
            latest_indication_date=self._first_str(
                indication,
                keys=("gmtrJobYmd", "jobYmd", "readingDate"),
            ),
            last_meter_reading_m3=self._first_float(
                indication,
                meter,
                keys=(
                    "indiCompensThisMonthVc",
                    "lastMonthIndicatorQty",
                    "meterValue",
                    "meterReading",
                    "replaceNumber",
                    "currentMeterValue",
                    "lastMeterReading",
                ),
            ),
            self_input_available=self._self_input_available(home),
        )

    async def async_submit_meter_reading(
        self,
        reading: int,
    ) -> MeterReadingSubmitResult:
        """Submit a customer self meter reading."""
        await self.validate()
        if not self._use_contract_num:
            raise KoreaGasAppApiError("Use contract number is required for submission")

        payload = {
            "thisMonthIndicatorCustomer": str(reading),
            "useContractNum": self._use_contract_num,
            "customerNum": self._customer_no or "",
        }

        response = await self._post_json("relay/indications/input", payload)
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

    async def _try_get_bill_summary(
        self,
        mode: str,
        *,
        only_unpay: str,
    ) -> Any:
        """Fetch bill summary rows when the endpoint is available."""
        try:
            return await self._get_bill_summary(mode, only_unpay=only_unpay)
        except KoreaGasAppApiError:
            return None

    async def _get_bill_summary(
        self,
        mode: str,
        *,
        only_unpay: str,
    ) -> Any:
        """Fetch bill summary rows."""
        return await self._get(
            "bills/summary",
            self._contract_params(
                onlyUnpay=only_unpay,
                f=mode,
            ),
        )

    def _contract_params(self, **extra: Any) -> dict[str, Any]:
        """Return request params, omitting unknown contract values."""
        params: dict[str, Any] = {"customerNum": self._customer_no or ""}
        if self._use_contract_num:
            params["useContractNum"] = self._use_contract_num
        params.update(extra)
        return params

    async def _try_get(self, path: str, params: dict[str, Any]) -> Any:
        """Run a best-effort GET request."""
        try:
            return await self._get(path, params)
        except KoreaGasAppApiError:
            return None

    @staticmethod
    def _home_bill(value: Any) -> dict[str, Any] | None:
        """Return the home bill card from a home response."""
        if not isinstance(value, dict):
            return None
        cards = value.get("cards")
        if not isinstance(cards, dict):
            return None
        bill = cards.get("bill")
        return bill if isinstance(bill, dict) else None

    @staticmethod
    def _home_indication(value: Any) -> dict[str, Any] | None:
        """Return the home indication card from a home response."""
        if not isinstance(value, dict):
            return None
        cards = value.get("cards")
        if not isinstance(cards, dict):
            return None
        indication = cards.get("indication")
        if isinstance(indication, dict):
            history = indication.get("history")
            if isinstance(history, list):
                first = next((item for item in history if isinstance(item, dict)), None)
                if first is not None:
                    return first
            return indication
        return None

    @staticmethod
    def _home_bill_history(value: Any) -> dict[str, Any] | None:
        """Return the latest item from the home bill history."""
        bill = KoreaGasAppClient._home_bill(value)
        if not isinstance(bill, dict):
            return None
        history = bill.get("history")
        if not isinstance(history, list):
            return None
        return next(
            (item for item in reversed(history) if isinstance(item, dict)),
            None,
        )

    @staticmethod
    def _self_input_available(value: Any) -> bool | None:
        """Return whether self meter reading is currently available."""
        if not isinstance(value, dict):
            return None
        cards = value.get("cards")
        if not isinstance(cards, dict):
            return None
        indication = cards.get("indication")
        if not isinstance(indication, dict):
            return None
        available = indication.get("selfInputAvailable")
        if available is None:
            return None
        return str(available).upper() == "Y"

    async def _get(
        self,
        path: str,
        params: dict[str, Any],
        *,
        headers: dict[str, str] | None = None,
    ) -> Any:
        """Run a GET request against the Gas App web API."""
        if self._session is None:
            raise KoreaGasAppEndpointUnknownError("HTTP session is not available")

        async with self._session.get(
            urljoin(self._base_url, path),
            params=params,
            headers=headers or self._headers,
        ) as response:
            await self._raise_for_status(response, "GET", path)
            return await response.json()

    async def _post_json(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        headers: dict[str, str] | None = None,
    ) -> Any:
        """Run a JSON POST request against the Gas App web API."""
        if self._session is None:
            raise KoreaGasAppEndpointUnknownError("HTTP session is not available")

        async with self._session.post(
            urljoin(self._base_url, path),
            json=payload,
            headers=headers or self._headers,
        ) as response:
            await self._raise_for_status(response, "POST", path)
            return await response.json()

    async def _put_json(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        headers: dict[str, str] | None = None,
    ) -> Any:
        """Run a PUT JSON request against the Gas App web API."""
        if self._session is None:
            raise KoreaGasAppEndpointUnknownError("HTTP session is not available")

        async with self._session.put(
            urljoin(self._base_url, path),
            json=payload,
            headers=headers or self._headers,
        ) as response:
            await self._raise_for_status(response, "PUT", path)
            if response.content_length == 0:
                return None
            text = await response.text()
            if not text:
                return None
            return await response.json()

    @property
    def _headers(self) -> dict[str, str]:
        """Return headers used by the Gas App web frontend."""
        return self._headers_with(
            auth_token=self._auth_token or "",
            member_no=self._member_no or "",
            company_code=self._company_code or "",
        )

    @property
    def _anonymous_headers(self) -> dict[str, str]:
        """Return headers used before a Gas App member session exists."""
        return self._headers_with(auth_token="", member_no="", company_code="0")

    def _headers_with(
        self,
        *,
        auth_token: str,
        member_no: str,
        company_code: str,
    ) -> dict[str, str]:
        """Return Gas App headers with explicit auth fields."""
        headers = {
            "Accept": "*/*",
            "User-Agent": self._user_agent,
            "X-VERSION": self._app_version,
            "X-PLATFORM": self._platform,
            "X-TOKEN": auth_token,
            "X-MEMBER": member_no,
            "X-COMPANY": company_code,
            "X-WEBVERSION": DEFAULT_WEB_VERSION,
        }
        if self._adid:
            headers["X-ADID"] = self._adid
        headers["X-TID"] = self._tid or ""
        if self._os_version:
            headers["X-OS-VERSION"] = self._os_version
        if self._device_name:
            headers["X-DEVICE-NAME"] = self._device_name
        if self._device_id:
            headers["X-DEVID"] = self._device_id
        return headers

    def _native_ios_headers(self, *, company_code: str, device_id: str) -> dict[str, str]:
        """Return headers used by the native iOS session endpoint."""
        return {
            "Accept": "*/*",
            "User-Agent": DEFAULT_IOS_USER_AGENT,
            "X-VERSION": DEFAULT_IOS_APP_VERSION,
            "X-PLATFORM": DEFAULT_IOS_PLATFORM,
            "X-TOKEN": self._auth_token or "",
            "X-MEMBER": self._member_no or "",
            "X-COMPANY": company_code,
            "X-ADID": self._adid or device_id,
            "X-WEBVERSION": DEFAULT_WEB_VERSION,
            "X-OS-VERSION": DEFAULT_IOS_OS_VERSION,
            "X-DEVICE-NAME": DEFAULT_IOS_DEVICE_NAME,
            "X-DEVID": device_id,
        }

    @staticmethod
    async def _raise_for_status(response: Any, method: str, path: str) -> None:
        """Raise a typed API error for unsuccessful responses."""
        if response.status == 401:
            raise KoreaGasAppAuthError("Gas App session token is invalid or expired")
        if response.status == 418:
            body = await response.text()
            _LOGGER.debug(
                "Gas App %s %s rejected with HTTP 418: %s",
                method,
                path,
                body[:200],
            )
            raise KoreaGasAppAuthError(
                "Gas App rejected the saved session; reauthentication is required"
            )
        if response.status >= 400:
            body = await response.text()
            raise KoreaGasAppApiError(
                f"Gas App API request failed: {response.status} {body[:200]}"
            )

    @staticmethod
    def _first_item(value: Any) -> dict[str, Any] | None:
        """Return the first object from an API response."""
        if isinstance(value, list):
            return next((item for item in value if isinstance(item, dict)), None)
        if isinstance(value, dict):
            data = value.get("data")
            if isinstance(data, list):
                return next((item for item in data if isinstance(item, dict)), None)
            return value
        return None

    @classmethod
    def _first_int(
        cls,
        *values: Any,
        keys: tuple[str, ...],
    ) -> int | None:
        """Find the first integer-ish value by key."""
        value = cls._first_value(*values, keys=keys)
        if value is None:
            return None
        if isinstance(value, str):
            value = value.replace(",", "").replace("원", "").strip()
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None

    @classmethod
    def _first_float(
        cls,
        *values: Any,
        keys: tuple[str, ...],
    ) -> float | None:
        """Find the first float-ish value by key."""
        value = cls._first_value(*values, keys=keys)
        if value is None:
            return None
        if isinstance(value, str):
            value = value.replace(",", "").replace("㎥", "").replace("m3", "").strip()
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _first_value(
        *values: Any,
        keys: tuple[str, ...],
    ) -> Any:
        """Find a value in nested dictionaries using likely response keys."""
        for value in values:
            if not isinstance(value, dict):
                continue
            for key in keys:
                if key in value and value[key] not in (None, ""):
                    return value[key]
        return None

    @classmethod
    def _first_str(
        cls,
        *values: Any,
        keys: tuple[str, ...],
    ) -> str | None:
        """Find the first non-empty string-ish value by key."""
        value = cls._first_value(*values, keys=keys)
        if value in (None, ""):
            return None
        return str(value)

    @staticmethod
    def _coerce_int(value: Any) -> int | None:
        """Coerce API integer-ish values."""
        if value is None:
            return None
        if isinstance(value, str):
            value = value.replace(",", "").strip()
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None

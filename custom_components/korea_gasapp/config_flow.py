"""Config flow for Korea Gas App."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import selector

from .api import KoreaGasAppApiError, KoreaGasAppAuthError, KoreaGasAppClient
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
    CONF_POLL_INTERVAL,
    CONF_READING_ENTITY_ID,
    CONF_SUBMIT_DAY,
    CONF_SUBMIT_TIME,
    CONF_TID,
    CONF_USER_AGENT,
    CONF_USE_CONTRACT_NUM,
    DEFAULT_APP_PLATFORM,
    DEFAULT_APP_VERSION,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_SUBMIT_DAY,
    DEFAULT_SUBMIT_TIME,
    DOMAIN,
)

CONF_BIRTHDAY = "birthday"
CONF_GENDER_CODE = "gender_code"
CONF_IDENTITY_NO = "identity_no"
CONF_MOBILE_CO = "mobile_co"
CONF_MOBILE_NO = "mobile_no"
CONF_NAME = "name"
CONF_OTP = "otp"

IOS_APP_VERSION = "4.3.7.27265"
IOS_DEVICE_NAME = "iPad"
IOS_OS_VERSION = "18.7"
IOS_PLATFORM = "IOS"
IOS_USER_AGENT = (
    "Mozilla/5.0 (iPad; CPU OS 18_7 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) WunderFlo iPhone/gasapp"
)

VALID_GENDER_CODES = {"1", "2", "3", "4"}

MOBILE_CO_OPTIONS = {
    "1": "SKT",
    "2": "KT",
    "3": "LG U+",
    "5": "SKT MVNO",
    "6": "KT MVNO",
    "7": "LG U+ MVNO",
}

class KoreaGasAppConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Korea Gas App."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> KoreaGasAppOptionsFlow:
        """Create the options flow."""
        return KoreaGasAppOptionsFlow(config_entry)

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Handle the initial step."""
        return await self.async_step_sms_login(user_input)

    async def async_step_manual_session(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Handle the manual session-value step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            errors, result = await self._async_validate_manual_session(user_input)
            if result is not None:
                return result

        return self.async_show_form(
            step_id="manual_session",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_ACCOUNT_ID): str,
                    vol.Required(CONF_USE_CONTRACT_NUM): str,
                    vol.Optional(CONF_CUSTOMER_NO, default=""): str,
                    vol.Required(CONF_AUTH_TOKEN): str,
                    vol.Required(CONF_MEMBER_NO): str,
                    vol.Required(CONF_COMPANY_CODE): str,
                    vol.Optional(CONF_PLATFORM, default=DEFAULT_APP_PLATFORM): str,
                    vol.Optional(CONF_APP_VERSION, default=DEFAULT_APP_VERSION): str,
                    vol.Optional(CONF_OS_VERSION): str,
                    vol.Optional(CONF_DEVICE_NAME): str,
                    vol.Optional(CONF_DEVICE_ID): str,
                    vol.Optional(CONF_USER_AGENT): str,
                    vol.Optional(CONF_ADID): str,
                    vol.Optional(CONF_TID): str,
                    vol.Required(
                        CONF_SUBMIT_DAY,
                        default=DEFAULT_SUBMIT_DAY,
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=1,
                            max=31,
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),
                    vol.Required(
                        CONF_SUBMIT_TIME,
                        default=DEFAULT_SUBMIT_TIME,
                    ): selector.TimeSelector(),
                    vol.Required(CONF_READING_ENTITY_ID): selector.EntitySelector(
                        selector.EntitySelectorConfig(
                            domain=["input_number", "number", "sensor"]
                        )
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_sms_login(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Request an SMS verification code."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                birthday = _birthday_from_identity(user_input[CONF_IDENTITY_NO])
                gender_code = _gender_code_from_identity(user_input[CONF_IDENTITY_NO])
            except vol.Invalid:
                errors[CONF_IDENTITY_NO] = "invalid_identity_no"
                birthday = ""
                gender_code = ""

            device_id = str(uuid4()).upper()
            auth_client = self._auth_client(device_id)
            if not errors:
                try:
                    sms_result = await auth_client.async_request_sms(
                        mobile_co=user_input[CONF_MOBILE_CO],
                        mobile_no=user_input[CONF_MOBILE_NO],
                        birthday=birthday,
                        gender_code=gender_code,
                        name=user_input[CONF_NAME],
                    )
                except KoreaGasAppApiError:
                    errors["base"] = "sms_request_failed"
                else:
                    self._sms_login = {
                        **user_input,
                        CONF_ADID: device_id,
                        CONF_DEVICE_ID: device_id,
                        CONF_BIRTHDAY: birthday,
                        CONF_GENDER_CODE: gender_code,
                        "request_no": sms_result.request_no,
                        "response_uniq_id": sms_result.response_uniq_id,
                    }
                    return await self.async_step_sms_confirm()
        return self.async_show_form(
            step_id="sms_login",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME): str,
                    vol.Required(CONF_MOBILE_NO): str,
                    vol.Required(CONF_IDENTITY_NO): str,
                    vol.Required(CONF_MOBILE_CO): vol.In(MOBILE_CO_OPTIONS),
                    vol.Required(
                        CONF_SUBMIT_DAY,
                        default=DEFAULT_SUBMIT_DAY,
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=1,
                            max=31,
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),
                    vol.Required(
                        CONF_SUBMIT_TIME,
                        default=DEFAULT_SUBMIT_TIME,
                    ): selector.TimeSelector(),
                    vol.Required(CONF_READING_ENTITY_ID): selector.EntitySelector(
                        selector.EntitySelectorConfig(
                            domain=["input_number", "number", "sensor"]
                        )
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_sms_confirm(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Confirm an SMS verification code and create the config entry."""
        errors: dict[str, str] = {}

        if user_input is not None:
            login = self._sms_login
            auth_client = self._auth_client(login[CONF_DEVICE_ID])
            try:
                confirm_result = await auth_client.async_confirm_sms(
                    request_no=login["request_no"],
                    response_uniq_id=login["response_uniq_id"],
                    otp=user_input[CONF_OTP],
                )
                member = await auth_client.async_create_member(
                    name=login[CONF_NAME],
                    birth_date=_birth_date(login[CONF_BIRTHDAY], login[CONF_GENDER_CODE]),
                    mobile_no=login[CONF_MOBILE_NO],
                    gender=_member_gender(login[CONF_GENDER_CODE]),
                    ci=confirm_result.ci,
                    di=confirm_result.di,
                    adid=login[CONF_ADID],
                )
                init_payload = await auth_client.async_get_init(
                    auth_token=member.auth_token,
                    member_no=member.member_no,
                    company_code="0",
                )
            except KoreaGasAppAuthError:
                errors["base"] = "invalid_otp"
            except KoreaGasAppApiError:
                errors["base"] = "login_failed"
            else:
                contracts = _contracts_from_init(init_payload)
                if not contracts:
                    errors["base"] = "no_contract"
                elif len(contracts) == 1:
                    return await self._async_create_sms_entry(
                        login=login,
                        member_no=member.member_no,
                        auth_token=member.auth_token,
                        contract=contracts[0],
                    )
                else:
                    self._sms_member = {
                        "member_no": member.member_no,
                        "auth_token": member.auth_token,
                        "contracts": contracts,
                    }
                    return await self.async_step_contract()

        return self.async_show_form(
            step_id="sms_confirm",
            data_schema=vol.Schema({vol.Required(CONF_OTP): str}),
            errors=errors,
        )

    async def async_step_contract(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Let the user pick one contract when multiple are available."""
        contracts = self._sms_member["contracts"]
        contract_map = {
            _contract_key(contract): contract
            for contract in contracts
        }

        if user_input is not None:
            return await self._async_create_sms_entry(
                login=self._sms_login,
                member_no=self._sms_member["member_no"],
                auth_token=self._sms_member["auth_token"],
                contract=contract_map[user_input[CONF_USE_CONTRACT_NUM]],
            )

        return self.async_show_form(
            step_id="contract",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USE_CONTRACT_NUM): vol.In(
                        {
                            key: _contract_label(contract)
                            for key, contract in contract_map.items()
                        }
                    )
                }
            ),
        )

    async def _async_validate_manual_session(
        self,
        user_input: dict[str, Any],
    ) -> tuple[dict[str, str], config_entries.ConfigFlowResult | None]:
        """Validate manually supplied session values."""
        errors: dict[str, str] = {}
        unique_id = user_input.get(CONF_USE_CONTRACT_NUM) or user_input.get(
            CONF_CUSTOMER_NO
        )
        if unique_id is None:
            errors["base"] = "missing_contract"
            return errors, None

        await self.async_set_unique_id(unique_id)
        self._abort_if_unique_id_configured()

        client = KoreaGasAppClient(
            session=None,  # type: ignore[arg-type]
            account_id=user_input.get(CONF_ACCOUNT_ID, unique_id or ""),
            customer_no=user_input.get(CONF_CUSTOMER_NO, ""),
            auth_token=user_input.get(CONF_AUTH_TOKEN),
            member_no=user_input.get(CONF_MEMBER_NO),
            company_code=user_input.get(CONF_COMPANY_CODE),
            use_contract_num=user_input.get(CONF_USE_CONTRACT_NUM),
            adid=user_input.get(CONF_ADID),
            tid=user_input.get(CONF_TID),
            app_version=user_input.get(CONF_APP_VERSION),
            platform=user_input.get(CONF_PLATFORM),
            os_version=user_input.get(CONF_OS_VERSION),
            device_name=user_input.get(CONF_DEVICE_NAME),
            device_id=user_input.get(CONF_DEVICE_ID),
            user_agent=user_input.get(CONF_USER_AGENT),
        )
        try:
            await client.validate()
        except KoreaGasAppAuthError:
            errors["base"] = "invalid_auth"
            return errors, None

        return errors, self.async_create_entry(
            title=unique_id or "Korea Gas App",
            data=user_input,
        )

    def _auth_client(self, device_id: str) -> KoreaGasAppClient:
        """Return a client configured like the captured iOS login flow."""
        return KoreaGasAppClient(
            async_get_clientsession(self.hass),
            account_id="",
            customer_no="",
            adid=device_id,
            app_version=IOS_APP_VERSION,
            platform=IOS_PLATFORM,
            os_version=IOS_OS_VERSION,
            device_name=IOS_DEVICE_NAME,
            device_id=device_id,
            user_agent=IOS_USER_AGENT,
        )

    async def _async_create_sms_entry(
        self,
        *,
        login: dict[str, Any],
        member_no: str,
        auth_token: str,
        contract: dict[str, Any],
    ) -> config_entries.ConfigFlowResult:
        """Create an entry from a completed SMS login."""
        unique_id = str(
            contract.get("useContractNum") or contract.get("customerNum") or member_no
        )
        await self.async_set_unique_id(unique_id)
        self._abort_if_unique_id_configured()

        data = {
            CONF_ACCOUNT_ID: unique_id,
            CONF_USE_CONTRACT_NUM: str(contract.get("useContractNum") or ""),
            CONF_CUSTOMER_NO: str(contract.get("customerNum") or ""),
            CONF_AUTH_TOKEN: auth_token,
            CONF_MEMBER_NO: member_no,
            CONF_COMPANY_CODE: str(contract.get("company") or "0"),
            CONF_PLATFORM: IOS_PLATFORM,
            CONF_APP_VERSION: IOS_APP_VERSION,
            CONF_OS_VERSION: IOS_OS_VERSION,
            CONF_DEVICE_NAME: IOS_DEVICE_NAME,
            CONF_DEVICE_ID: login[CONF_DEVICE_ID],
            CONF_USER_AGENT: IOS_USER_AGENT,
            CONF_ADID: login[CONF_ADID],
            CONF_SUBMIT_DAY: login[CONF_SUBMIT_DAY],
            CONF_SUBMIT_TIME: login[CONF_SUBMIT_TIME],
            CONF_READING_ENTITY_ID: login[CONF_READING_ENTITY_ID],
        }
        return self.async_create_entry(title=_contract_label(contract), data=data)


def _birth_date(birthday: str, gender_code: str) -> str:
    """Convert YYMMDD plus Korean gender code to YYYYMMDD."""
    century = "20" if gender_code in {"3", "4"} else "19"
    return f"{century}{birthday}"


def _normalize_identity_no(value: str) -> str:
    """Normalize a partial Korean resident number to YYMMDD-G."""
    normalized = value.strip()
    if len(normalized) >= 8 and normalized[6] == "-":
        birthday = normalized[:6]
        gender_code = normalized[7]
    elif len(normalized) >= 7:
        birthday = normalized[:6]
        gender_code = normalized[6]
    else:
        raise vol.Invalid("invalid_identity_no")

    if not birthday.isdigit() or gender_code not in VALID_GENDER_CODES:
        raise vol.Invalid("invalid_identity_no")
    return f"{birthday}-{gender_code}"


def _birthday_from_identity(value: str) -> str:
    """Return YYMMDD from a normalized partial resident number."""
    return _normalize_identity_no(value)[:6]


def _gender_code_from_identity(value: str) -> str:
    """Return the gender code from a normalized partial resident number."""
    return _normalize_identity_no(value)[7]


def _member_gender(gender_code: str) -> str:
    """Convert NICE gender code to the Gas App member gender value."""
    return "F" if gender_code in {"2", "4"} else "M"


def _contracts_from_init(init_payload: Any) -> list[dict[str, Any]]:
    """Extract contract dictionaries from the app init payload."""
    if not isinstance(init_payload, dict):
        return []
    contracts = init_payload.get("contracts")
    if not isinstance(contracts, list):
        return []
    return [contract for contract in contracts if isinstance(contract, dict)]


def _contract_key(contract: dict[str, Any]) -> str:
    """Return a stable key for a contract selector."""
    return str(contract.get("useContractNum") or contract.get("customerNum") or "")


def _contract_label(contract: dict[str, Any]) -> str:
    """Return a human-friendly contract title without exposing address details."""
    alias = contract.get("alias")
    label = contract.get("label")
    use_contract_num = contract.get("useContractNum")
    return str(alias or label or use_contract_num or "Korea Gas App")


class KoreaGasAppOptionsFlow(config_entries.OptionsFlow):
    """Handle Korea Gas App options."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Manage options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_POLL_INTERVAL,
                        default=self._config_entry.options.get(
                            CONF_POLL_INTERVAL,
                            DEFAULT_POLL_INTERVAL,
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=5, max=1440)),
                    vol.Optional(
                        CONF_SUBMIT_DAY,
                        default=self._config_entry.options.get(
                            CONF_SUBMIT_DAY,
                            self._config_entry.data.get(
                                CONF_SUBMIT_DAY,
                                DEFAULT_SUBMIT_DAY,
                            ),
                        ),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=1,
                            max=31,
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),
                    vol.Optional(
                        CONF_SUBMIT_TIME,
                        default=self._config_entry.options.get(
                            CONF_SUBMIT_TIME,
                            self._config_entry.data.get(
                                CONF_SUBMIT_TIME,
                                DEFAULT_SUBMIT_TIME,
                            ),
                        ),
                    ): selector.TimeSelector(),
                    vol.Optional(
                        CONF_READING_ENTITY_ID,
                        default=self._config_entry.options.get(
                            CONF_READING_ENTITY_ID,
                            self._config_entry.data.get(CONF_READING_ENTITY_ID),
                        )
                        or "",
                    ): selector.EntitySelector(
                        selector.EntitySelectorConfig(
                            domain=["input_number", "number", "sensor"]
                        )
                    ),
                }
            ),
        )


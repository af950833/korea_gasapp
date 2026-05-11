"""Config flow for Korea Gas App."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import selector

# .api is intentionally NOT imported at module level.
# HA loads config_flow while __init__.py is still initialising (which itself
# imports api), so a top-level "from .api import ..." here would encounter a
# partially-initialised api module and raise ImportError.
# Instead, each method that needs api symbols imports them locally.

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
    CONF_READING_ENTITY_ID,
    CONF_READING_ROUND,
    CONF_TID,
    CONF_USER_AGENT,
    CONF_USE_CONTRACT_NUM,
    DEFAULT_APP_PLATFORM,
    DEFAULT_APP_VERSION,
    DEFAULT_READING_ROUND,
    DOMAIN,
    IOS_APP_VERSION,
    IOS_DEVICE_NAME,
    IOS_OS_VERSION,
    IOS_PLATFORM,
    IOS_USER_AGENT,
    READING_ROUND_DOWN,
    READING_ROUND_UP,
)

# ── Flow-only config keys (not persisted in config entry data) ────────────────
_CONF_BIRTHDAY = "birthday"
_CONF_GENDER_CODE = "gender_code"
_CONF_IDENTITY_NO = "identity_no"
_CONF_MOBILE_CO = "mobile_co"
_CONF_MOBILE_NO = "mobile_no"
_CONF_NAME = "name"
_CONF_OTP = "otp"

_VALID_GENDER_CODES = {"1", "2", "3", "4"}

_MOBILE_CO_OPTIONS = {
    "1": "SKT",
    "2": "KT",
    "3": "LG U+",
    "5": "SKT MVNO",
    "6": "KT MVNO",
    "7": "LG U+ MVNO",
}

_READING_ROUND_SELECTOR = selector.SelectSelector(
    selector.SelectSelectorConfig(
        options=[
            selector.SelectOptionDict(value=READING_ROUND_UP,   label="올림 (ceil)"),
            selector.SelectOptionDict(value=READING_ROUND_DOWN, label="내림 (floor)"),
        ],
        mode=selector.SelectSelectorMode.LIST,
    )
)


def _reading_fields(defaults: dict[str, Any] | None = None) -> dict[vol.Marker, Any]:
    """Return the two user-facing reading-submission config fields."""
    d = defaults or {}
    return {
        vol.Required(
            CONF_READING_ENTITY_ID,
            default=d.get(CONF_READING_ENTITY_ID, ""),
        ): selector.EntitySelector(
            selector.EntitySelectorConfig(domain=["input_number", "number", "sensor"])
        ),
        vol.Required(
            CONF_READING_ROUND,
            default=d.get(CONF_READING_ROUND, DEFAULT_READING_ROUND),
        ): _READING_ROUND_SELECTOR,
    }


class KoreaGasAppConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Korea Gas App."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> KoreaGasAppOptionsFlow:
        return KoreaGasAppOptionsFlow(config_entry)

    # ── Step routing ──────────────────────────────────────────────────────

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        return await self.async_step_sms_login(user_input)

    # ── SMS login ─────────────────────────────────────────────────────────

    async def async_step_sms_login(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Collect identity info, validate it, and request an SMS code."""
        from .api import KoreaGasAppApiError  # lazy import — see module docstring

        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                birthday = _birthday_from_identity(user_input[_CONF_IDENTITY_NO])
                gender_code = _gender_code_from_identity(user_input[_CONF_IDENTITY_NO])
            except vol.Invalid:
                errors[_CONF_IDENTITY_NO] = "invalid_identity_no"
            else:
                device_id = str(uuid4()).upper()
                try:
                    sms_result = await self._auth_client(device_id).async_request_sms(
                        mobile_co=user_input[_CONF_MOBILE_CO],
                        mobile_no=user_input[_CONF_MOBILE_NO],
                        birthday=birthday,
                        gender_code=gender_code,
                        name=user_input[_CONF_NAME],
                    )
                except KoreaGasAppApiError:
                    errors["base"] = "sms_request_failed"
                else:
                    self._sms_login: dict[str, Any] = {
                        **user_input,
                        _CONF_BIRTHDAY:     birthday,
                        _CONF_GENDER_CODE:  gender_code,
                        CONF_ADID:          device_id,
                        CONF_DEVICE_ID:     device_id,
                        "request_no":        sms_result.request_no,
                        "response_uniq_id":  sms_result.response_uniq_id,
                    }
                    return await self.async_step_sms_confirm()

        return self.async_show_form(
            step_id="sms_login",
            data_schema=vol.Schema({
                vol.Required(_CONF_NAME):        str,
                vol.Required(_CONF_MOBILE_NO):   str,
                vol.Required(_CONF_IDENTITY_NO): str,
                vol.Required(_CONF_MOBILE_CO):   vol.In(_MOBILE_CO_OPTIONS),
                **_reading_fields(),
            }),
            errors=errors,
        )

    async def async_step_sms_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Verify the SMS OTP and create a member session."""
        from .api import KoreaGasAppApiError, KoreaGasAppAuthError  # lazy import

        errors: dict[str, str] = {}

        if user_input is not None:
            login = self._sms_login
            client = self._auth_client(login[CONF_DEVICE_ID])
            try:
                confirm = await client.async_confirm_sms(
                    request_no=login["request_no"],
                    response_uniq_id=login["response_uniq_id"],
                    otp=user_input[_CONF_OTP],
                )
                member = await client.async_create_member(
                    name=login[_CONF_NAME],
                    birth_date=_birth_date(login[_CONF_BIRTHDAY], login[_CONF_GENDER_CODE]),
                    mobile_no=login[_CONF_MOBILE_NO],
                    gender=_member_gender(login[_CONF_GENDER_CODE]),
                    ci=confirm.ci,
                    di=confirm.di,
                    adid=login[CONF_ADID],
                )
                init_payload = await client.async_get_init(
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
                    return await self._create_sms_entry(
                        login=login,
                        member_no=member.member_no,
                        auth_token=member.auth_token,
                        contract=contracts[0],
                    )
                else:
                    self._sms_member = {
                        "member_no":  member.member_no,
                        "auth_token": member.auth_token,
                        "contracts":  contracts,
                    }
                    return await self.async_step_contract()

        return self.async_show_form(
            step_id="sms_confirm",
            data_schema=vol.Schema({vol.Required(_CONF_OTP): str}),
            errors=errors,
        )

    async def async_step_contract(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Let the user pick one contract when the account has multiple."""
        contracts = self._sms_member["contracts"]
        contract_map = {_contract_key(c): c for c in contracts}

        if user_input is not None:
            return await self._create_sms_entry(
                login=self._sms_login,
                member_no=self._sms_member["member_no"],
                auth_token=self._sms_member["auth_token"],
                contract=contract_map[user_input[CONF_USE_CONTRACT_NUM]],
            )

        return self.async_show_form(
            step_id="contract",
            data_schema=vol.Schema({
                vol.Required(CONF_USE_CONTRACT_NUM): vol.In(
                    {k: _contract_label(c) for k, c in contract_map.items()}
                )
            }),
        )

    async def async_step_manual_session(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Alternative setup path: enter session values captured from the app."""
        errors: dict[str, str] = {}

        if user_input is not None:
            errors, result = await self._validate_manual_session(user_input)
            if result is not None:
                return result

        return self.async_show_form(
            step_id="manual_session",
            data_schema=vol.Schema({
                vol.Optional(CONF_ACCOUNT_ID):                  str,
                vol.Required(CONF_USE_CONTRACT_NUM):            str,
                vol.Optional(CONF_CUSTOMER_NO, default=""):    str,
                vol.Required(CONF_AUTH_TOKEN):                  str,
                vol.Required(CONF_MEMBER_NO):                   str,
                vol.Required(CONF_COMPANY_CODE):                str,
                vol.Optional(CONF_PLATFORM,    default=DEFAULT_APP_PLATFORM): str,
                vol.Optional(CONF_APP_VERSION, default=DEFAULT_APP_VERSION):  str,
                vol.Optional(CONF_OS_VERSION):  str,
                vol.Optional(CONF_DEVICE_NAME): str,
                vol.Optional(CONF_DEVICE_ID):   str,
                vol.Optional(CONF_USER_AGENT):  str,
                vol.Optional(CONF_ADID):        str,
                vol.Optional(CONF_TID):         str,
                **_reading_fields(),
            }),
            errors=errors,
        )

    # ── Private helpers ───────────────────────────────────────────────────

    def _auth_client(self, device_id: str):  # type: ignore[return]
        """Return a client configured with the captured iOS session profile."""
        from .api import KoreaGasAppClient  # lazy import

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

    async def _create_sms_entry(
        self,
        *,
        login: dict[str, Any],
        member_no: str,
        auth_token: str,
        contract: dict[str, Any],
    ) -> config_entries.ConfigFlowResult:
        unique_id = str(
            contract.get("useContractNum") or contract.get("customerNum") or member_no
        )
        await self.async_set_unique_id(unique_id)
        self._abort_if_unique_id_configured()

        return self.async_create_entry(
            title=_contract_label(contract),
            data={
                CONF_ACCOUNT_ID:        unique_id,
                CONF_USE_CONTRACT_NUM:  str(contract.get("useContractNum") or ""),
                CONF_CUSTOMER_NO:       str(contract.get("customerNum") or ""),
                CONF_AUTH_TOKEN:        auth_token,
                CONF_MEMBER_NO:         member_no,
                CONF_COMPANY_CODE:      str(contract.get("company") or "0"),
                CONF_PLATFORM:          IOS_PLATFORM,
                CONF_APP_VERSION:       IOS_APP_VERSION,
                CONF_OS_VERSION:        IOS_OS_VERSION,
                CONF_DEVICE_NAME:       IOS_DEVICE_NAME,
                CONF_DEVICE_ID:         login[CONF_DEVICE_ID],
                CONF_USER_AGENT:        IOS_USER_AGENT,
                CONF_ADID:              login[CONF_ADID],
                CONF_READING_ENTITY_ID: login[CONF_READING_ENTITY_ID],
                CONF_READING_ROUND:     login.get(CONF_READING_ROUND, DEFAULT_READING_ROUND),
            },
        )

    async def _validate_manual_session(
        self, user_input: dict[str, Any]
    ) -> tuple[dict[str, str], config_entries.ConfigFlowResult | None]:
        from .api import KoreaGasAppAuthError, KoreaGasAppClient  # lazy import

        errors: dict[str, str] = {}
        unique_id = user_input.get(CONF_USE_CONTRACT_NUM) or user_input.get(CONF_CUSTOMER_NO)
        if not unique_id:
            errors["base"] = "missing_contract"
            return errors, None

        await self.async_set_unique_id(unique_id)
        self._abort_if_unique_id_configured()

        client = KoreaGasAppClient(
            session=None,  # type: ignore[arg-type]
            account_id=user_input.get(CONF_ACCOUNT_ID, unique_id),
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

        return errors, self.async_create_entry(title=unique_id, data=user_input)


class KoreaGasAppOptionsFlow(config_entries.OptionsFlow):
    """Options flow: only reading entity and rounding method are user-configurable."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        entry = self._config_entry
        current = {
            CONF_READING_ENTITY_ID: entry.options.get(
                CONF_READING_ENTITY_ID, entry.data.get(CONF_READING_ENTITY_ID, "")
            ),
            CONF_READING_ROUND: entry.options.get(
                CONF_READING_ROUND, entry.data.get(CONF_READING_ROUND, DEFAULT_READING_ROUND)
            ),
        }
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(_reading_fields(current)),
        )


# ── Pure helpers ──────────────────────────────────────────────────────────────

def _birth_date(birthday: str, gender_code: str) -> str:
    """Convert YYMMDD + NICE gender code to YYYYMMDD."""
    century = "20" if gender_code in {"3", "4"} else "19"
    return f"{century}{birthday}"


def _normalize_identity_no(value: str) -> str:
    """Parse partial resident number (YYMMDD-G or YYMMDDG) to YYMMDD-G."""
    s = value.strip()
    if len(s) >= 8 and s[6] == "-":
        birthday, gender_code = s[:6], s[7]
    elif len(s) >= 7:
        birthday, gender_code = s[:6], s[6]
    else:
        raise vol.Invalid("invalid_identity_no")
    if not birthday.isdigit() or gender_code not in _VALID_GENDER_CODES:
        raise vol.Invalid("invalid_identity_no")
    return f"{birthday}-{gender_code}"


def _birthday_from_identity(value: str) -> str:
    return _normalize_identity_no(value)[:6]


def _gender_code_from_identity(value: str) -> str:
    return _normalize_identity_no(value)[7]


def _member_gender(gender_code: str) -> str:
    return "F" if gender_code in {"2", "4"} else "M"


def _contracts_from_init(init_payload: Any) -> list[dict[str, Any]]:
    if not isinstance(init_payload, dict):
        return []
    contracts = init_payload.get("contracts")
    if not isinstance(contracts, list):
        return []
    return [c for c in contracts if isinstance(c, dict)]


def _contract_key(contract: dict[str, Any]) -> str:
    return str(contract.get("useContractNum") or contract.get("customerNum") or "")


def _contract_label(contract: dict[str, Any]) -> str:
    return str(
        contract.get("alias")
        or contract.get("label")
        or contract.get("useContractNum")
        or "Korea Gas App"
    )

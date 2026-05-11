"""Shared helpers for Korea Gas App entities."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .const import DOMAIN

if TYPE_CHECKING:
    # Import only for type checking to avoid any runtime circular dependency.
    from .coordinator import KoreaGasAppDataUpdateCoordinator


def get_account_id(coordinator: KoreaGasAppDataUpdateCoordinator) -> str:
    """Return the stable account ID used in unique_ids and entity_ids.

    Prefers use_contract_num, falls back to customer_no, then 'unknown'.
    Called at entity construction time, so coordinator.data should be available.
    """
    if coordinator.data:
        return (
            coordinator.data.use_contract_num
            or coordinator.data.customer_no
            or "unknown"
        )
    return "unknown"


def build_device_info(account_id: str) -> dict[str, Any]:
    """Build a device_info dict that groups all entities for one account.

    Each account gets its own HA device so that multi-account setups show
    separate cards in the UI.
    """
    return {
        "identifiers": {(DOMAIN, account_id)},
        "name": f"Gas account {account_id}",
        "manufacturer": "Korea Gas App",
        "model": "가스앱 계정",
    }

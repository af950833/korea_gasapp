"""Shared helpers for Korea Gas App entities."""

from __future__ import annotations

from typing import Any

from .coordinator import KoreaGasAppDataUpdateCoordinator


def get_account_id(coordinator: KoreaGasAppDataUpdateCoordinator) -> str:
    """Return a stable account identifier string for use in unique IDs and entity IDs."""
    if coordinator.data:
        return (
            coordinator.data.use_contract_num
            or coordinator.data.customer_no
            or "unknown"
        )
    return "unknown"


def build_device_info(account_id: str) -> dict[str, Any]:
    """Return a device_info dict that groups all entities for one account under one device."""
    return {
        "identifiers": {("korea_gasapp", account_id)},
        "name": f"Gas account {account_id}",
        "manufacturer": "Korea Gas App",
        "model": "가스앱 계정",
    }

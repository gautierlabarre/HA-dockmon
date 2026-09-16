"""Tests for the DockMon config flow."""
import aiohttp
import pytest
from homeassistant.config_entries import SOURCE_USER
from homeassistant.data_entry_flow import FlowResultType

from custom_components.dockmon.const import (
    CONF_API_KEY,
    CONF_URL,
    CONF_VERIFY_SSL,
    DOMAIN,
)

from .conftest import HOSTS, URL

USER_INPUT = {CONF_URL: f"{URL}/", CONF_API_KEY: "s3cret"}


class FakeSSLError(aiohttp.ClientSSLError):
    """A ClientSSLError that can be built without a live connection key."""

    def __init__(self) -> None:  # noqa: D107
        pass

    def __str__(self) -> str:
        return "certificate verify failed: self-signed certificate"


async def _start_flow(hass):
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )


async def test_form_is_shown_first(hass):
    result = await _start_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {}


async def test_successful_setup_creates_the_entry(hass, mock_api):
    result = await _start_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == f"DockMon ({HOSTS[0]['name']})"
    # The trailing slash is normalised away before it is stored.
    assert result["data"] == {
        CONF_URL: URL,
        CONF_API_KEY: "s3cret",
        CONF_VERIFY_SSL: True,
    }
    assert result["result"].unique_id == f"dockmon_{URL}"


@pytest.mark.parametrize(
    ("status", "expected_error"),
    [
        (401, "invalid_auth"),
        (403, "invalid_auth"),
        (500, "cannot_connect"),
        (404, "cannot_connect"),
    ],
)
async def test_api_errors_are_reported_on_the_form(
    hass, aioclient_mock, status, expected_error
):
    aioclient_mock.get(f"{URL}/api/hosts", status=status)

    result = await _start_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": expected_error}


async def test_unreachable_host_is_reported_on_the_form(hass, aioclient_mock):
    aioclient_mock.get(f"{URL}/api/hosts", exc=TimeoutError)

    result = await _start_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_a_bad_certificate_is_reported_on_the_form(hass, aioclient_mock):
    aioclient_mock.get(f"{URL}/api/hosts", exc=FakeSSLError())

    result = await _start_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_certificate"}


async def test_the_form_can_be_retried_after_an_error(hass, aioclient_mock):
    aioclient_mock.get(f"{URL}/api/hosts", status=401)

    result = await _start_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["errors"] == {"base": "invalid_auth"}

    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{URL}/api/hosts", json=HOSTS)
    aioclient_mock.get(f"{URL}/api/containers", json=[])

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_the_same_instance_cannot_be_added_twice(hass, mock_api, config_entry):
    result = await _start_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth_replaces_the_api_key(hass, mock_api, config_entry):
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    result = await config_entry.start_reauth_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: "fresh-key"}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert config_entry.data[CONF_API_KEY] == "fresh-key"
    # Everything else about the entry is left alone.
    assert config_entry.data[CONF_URL] == URL


async def test_reauth_rejects_a_key_that_is_still_invalid(
    hass, aioclient_mock, config_entry
):
    aioclient_mock.get(f"{URL}/api/hosts", status=401)

    result = await config_entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: "still-wrong"}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}
    assert config_entry.data[CONF_API_KEY] == "s3cret"


async def test_a_rejected_key_while_polling_opens_a_reauth_flow(
    hass, aioclient_mock, config_entry
):
    aioclient_mock.get(f"{URL}/api/hosts", status=401)

    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert len(flows) == 1
    assert flows[0]["context"]["source"] == "reauth"
    assert flows[0]["context"]["entry_id"] == config_entry.entry_id

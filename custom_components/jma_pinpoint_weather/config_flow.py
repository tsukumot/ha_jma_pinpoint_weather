from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    DOMAIN,
    CONF_NC_INTERVAL,
    DEF_NC_INTERVAL,
    MIN_NC_INTERVAL,
    MAX_NC_INTERVAL,
    CONF_NC_THRESHOLD,
    DEF_NC_THRESHOLD,
    MIN_NC_THRESHOLD,
    MAX_NC_THRESHOLD,
    CONF_LNC_THRESHOLD,
    DEF_LNC_THRESHOLD,
    MIN_LNC_THRESHOLD,
    MAX_LNC_THRESHOLD,
    CONF_GNC_THRESHOLD,
    DEF_GNC_THRESHOLD,
    MIN_GNC_THRESHOLD,
    MAX_GNC_THRESHOLD,
)

class RainForecastConfigFlow(ConfigFlow, domain=DOMAIN):
    """設定フロー"""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        # フォームが送信されると user_input に値が入る
        if user_input is not None:
            loc = user_input["location"]
            lat = loc["latitude"]
            lon = loc["longitude"]

            # 同じ地点の二重登録を防ぐ
            await self.async_set_unique_id(f"{lat:.4f}_{lon:.4f}")
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=user_input["name"],
                data={"name": user_input["name"], "latitude": lat, "longitude": lon},
            )

        # 初回表示: 初期値はHAに登録されている自宅の位置
        schema = vol.Schema(
            {
                vol.Required("name", default="自宅"): str,
                vol.Required(
                    "location",
                    default={
                        "latitude": self.hass.config.latitude,
                        "longitude": self.hass.config.longitude,
                    },
                ): selector.LocationSelector(
                    selector.LocationSelectorConfig(radius=False)
                ),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return RainForecastOptionsFlow()


class RainForecastOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        current = self.config_entry.options.get(CONF_NC_INTERVAL, DEF_NC_INTERVAL)
        schema = vol.Schema(
            {
                vol.Required(CONF_NC_INTERVAL, default=current): vol.All(
                    selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=MIN_NC_INTERVAL,
                            max=MAX_NC_INTERVAL,
                            step=1,
                            unit_of_measurement="分",
                            mode=selector.NumberSelectorMode.SLIDER,
                        )
                    ),
                    vol.Coerce(int),
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
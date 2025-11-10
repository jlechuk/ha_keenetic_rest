# noqa: D100

from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfDataRate, UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    SIGNAL_NEW_NETWORK_CLIENTS,
    UPDATE_COORDINATOR_CLIENTS_RX_SPEED,
    UPDATE_COORDINATOR_CLIENTS_TX_SPEED,
    UPDATE_COORDINATOR_IF_STATS,
    UPDATE_COORDINATOR_SYS_STATS,
    BaseKeeneticEntityDescription,
)
from .entity import (
    BaseKeeneticNetworkClientEntity,
    BaseKeeneticRouterEntity,
    add_network_client_entities,
)
from .router import KeeneticRouter


class GeneralRouterSensor(BaseKeeneticRouterEntity, SensorEntity):
    """Router sensor."""


class RouterWANSpeedSensor(GeneralRouterSensor):
    """Router WAN speed sensor."""
    def _get_coordinator_data(self) -> Any:
        if self.router.wan_interface_name:
            return super()._get_coordinator_data().\
                get(self.router.wan_interface_name, {})
        return {}


class NetworkClientSpeedSensor(BaseKeeneticNetworkClientEntity, SensorEntity):
    """Network client sensor."""
    def _get_attributes_data(self) -> dict:
        if data := self.router.get_network_clients_data():
            return data.get(self.client_id, {})
        return {}


@dataclass
class RouterSensorDescription(
    BaseKeeneticEntityDescription, SensorEntityDescription):
    """Router sensor description."""
    entity_class = GeneralRouterSensor


@dataclass
class NetworkClientSensorDescription(
    BaseKeeneticEntityDescription, SensorEntityDescription):
    """Network client sensor description."""


ROUTER_SENSORS: tuple[RouterSensorDescription, ...] = (
    RouterSensorDescription(
        key="cpuload",
        translation_key="cpuload",
        device_class=SensorDeviceClass.POWER_FACTOR,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        update_coordinator = UPDATE_COORDINATOR_SYS_STATS
    ),
    RouterSensorDescription(
        key="memory_usage",
        translation_key="memory_usage",
        device_class=SensorDeviceClass.POWER_FACTOR,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        update_coordinator = UPDATE_COORDINATOR_SYS_STATS,
        extra_attributes = {"Memory free": "memfree",
                            "Memory total": "memtotal"}
    ),
    RouterSensorDescription(
        key="uptime",
        translation_key="uptime",
        device_class=SensorDeviceClass.DURATION,
        state_class=None,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_display_precision=0,
        update_coordinator = UPDATE_COORDINATOR_SYS_STATS
    ),
    RouterSensorDescription(
        key="rxspeed",
        translation_key="wan_rx_speed",
        device_class=SensorDeviceClass.DATA_RATE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfDataRate.BITS_PER_SECOND,
        suggested_unit_of_measurement=UnitOfDataRate.KILOBITS_PER_SECOND,
        suggested_display_precision=0,
        update_coordinator=UPDATE_COORDINATOR_IF_STATS,
        entity_class=RouterWANSpeedSensor
    ),
        RouterSensorDescription(
        key="txspeed",
        translation_key="wan_tx_speed",
        device_class=SensorDeviceClass.DATA_RATE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfDataRate.BITS_PER_SECOND,
        suggested_unit_of_measurement=UnitOfDataRate.KILOBITS_PER_SECOND,
        suggested_display_precision=0,
        update_coordinator=UPDATE_COORDINATOR_IF_STATS,
        entity_class=RouterWANSpeedSensor
    )
)

NETWORK_CLIENT_SENSORS: tuple[NetworkClientSensorDescription, ...] = (
    NetworkClientSensorDescription(
        key="rxspeed",
        translation_key="rxspeed",
        device_class=SensorDeviceClass.DATA_RATE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfDataRate.BITS_PER_SECOND,
        suggested_unit_of_measurement=UnitOfDataRate.KILOBITS_PER_SECOND,
        suggested_display_precision=0,
        update_coordinator=UPDATE_COORDINATOR_CLIENTS_RX_SPEED,
        extra_attributes = {"Interface ID": {"interface": "id"},
                            "Interface name": {"interface": "name"}},
        entity_class=NetworkClientSpeedSensor
    ),
    NetworkClientSensorDescription(
        key="txspeed",
        translation_key="txspeed",
        device_class=SensorDeviceClass.DATA_RATE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfDataRate.BITS_PER_SECOND,
        suggested_unit_of_measurement=UnitOfDataRate.KILOBITS_PER_SECOND,
        suggested_display_precision=0,
        update_coordinator=UPDATE_COORDINATOR_CLIENTS_TX_SPEED,
        extra_attributes = {"Interface ID": {"interface": "id"},
                            "Interface name": {"interface": "name"}},
        entity_class=NetworkClientSpeedSensor
    )
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback
) -> None:
    """Add Router and Network clients sensors."""
    router: KeeneticRouter = hass.data[DOMAIN][config_entry.entry_id]

    # Add Router sensors
    router_sensors = [
        description.entity_class(
            router, description
        ) for description in ROUTER_SENSORS
    ]
    async_add_entities(router_sensors)

    # Add current Network clients sensors
    add_network_client_entities(router, router.tracked_network_client_ids,
                               NETWORK_CLIENT_SENSORS, async_add_entities)

    # Add sensors for new Network clients
    @callback
    def _add_new_client_sensors(new_client_ids) -> None:
        add_network_client_entities(router, new_client_ids,
                                   NETWORK_CLIENT_SENSORS,
                                   async_add_entities)

    config_entry.async_on_unload(
        async_dispatcher_connect(
            hass, SIGNAL_NEW_NETWORK_CLIENTS, _add_new_client_sensors
        )
    )


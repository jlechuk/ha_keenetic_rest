# noqa: D100

from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfDataRate, UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    DOMAIN,
    UPDATE_COORDINATOR_CLIENTS,
    UPDATE_COORDINATOR_RX,
    UPDATE_COORDINATOR_STAT,
    UPDATE_COORDINATOR_TX,
    BaseSensorDescription,
    NetworkClientSensorDescription,
)
from .entity import BaseSensor, NetworkClientBaseSensor, add_network_client_sensors
from .router import KeeneticRouter


@dataclass
class KeeneticSensorDescription(BaseSensorDescription):
    """Keenetic sensor description."""


KEENETIC_SENSORS: tuple[KeeneticSensorDescription, ...] = (
    KeeneticSensorDescription(
        key="cpuload",
        translation_key="cpuload",
        device_class=SensorDeviceClass.POWER_FACTOR,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        update_coordinator = UPDATE_COORDINATOR_STAT
    ),
    KeeneticSensorDescription(
        key="memory_usage",
        translation_key="memory_usage",
        device_class=SensorDeviceClass.POWER_FACTOR,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        update_coordinator = UPDATE_COORDINATOR_STAT,
        extra_attributes = ["memfree", "memtotal"]
    ),
    KeeneticSensorDescription(
        key="uptime",
        translation_key="uptime",
        device_class=SensorDeviceClass.DURATION,
        state_class=None,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_display_precision=0,
        update_coordinator = UPDATE_COORDINATOR_STAT
    ),
)

NETWORK_CLIENT_SENSORS: tuple[NetworkClientSensorDescription, ...] = (
    NetworkClientSensorDescription(
        key="rxspeed",
        translation_key="rxspeed",
        device_class=SensorDeviceClass.DATA_RATE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfDataRate.BITS_PER_SECOND,
        suggested_display_precision=0,
        update_coordinator=UPDATE_COORDINATOR_RX
    ),
    NetworkClientSensorDescription(
        key="txspeed",
        translation_key="txspeed",
        device_class=SensorDeviceClass.DATA_RATE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfDataRate.BITS_PER_SECOND,
        suggested_display_precision=0,
        update_coordinator=UPDATE_COORDINATOR_TX
    )
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback
) -> None:
    """Add Keentic router and Network clients SENSOR entities."""
    router: KeeneticRouter = hass.data[DOMAIN][config_entry.entry_id]
    tracked_client_ids = set()

    # Add Keentic router sensors
    keenetic_sensors = [
        KeeneticSensor(
            router,
            description,
        ) for description in KEENETIC_SENSORS
    ]
    async_add_entities(keenetic_sensors)

    # Add sensors for new Network clients
    clients_coordinator: DataUpdateCoordinator = router.\
        update_coordinators[UPDATE_COORDINATOR_CLIENTS]

    @callback
    def _add_new_client_sensors() -> None:
        new_client_ids = set(clients_coordinator.data.keys()).\
            difference(tracked_client_ids)
        tracked_client_ids.update(new_client_ids)

        add_network_client_sensors(
            router,
            new_client_ids,
            NETWORK_CLIENT_SENSORS,
            NetworkClientSensor,
            async_add_entities
        )

    config_entry.async_on_unload(
        clients_coordinator.async_add_listener(_add_new_client_sensors)
    )

    # Add current Network clients sensors
    _add_new_client_sensors()


class KeeneticSensor(BaseSensor, SensorEntity):
    """Keenetic router sensor."""
    def __init__(  # noqa: D107
        self,
        router: KeeneticRouter,
        entity_description: BaseSensorDescription
    ) -> None:
        super().__init__(router, entity_description)
        self._attr_unique_id = \
            f"{router.unique_id}-{entity_description.key}".lower()

    @property
    def native_value(self) -> float | int | str | None:  # noqa: D102
        return self.coordinator.data[self.entity_description.key]

    @property
    def extra_state_attributes(self) -> dict:  # noqa: D102
        attributes = self.entity_description.extra_attributes
        if attributes:
            return {
                attr: self.coordinator.data[attr] for attr in attributes
            }
        return {}

    @property
    def device_info(self) -> DeviceInfo:
        """Keenetic router device info."""
        return self.router.device_info


class NetworkClientSensor(NetworkClientBaseSensor, SensorEntity):
    """Network client sensor."""
    @property
    def native_value(self) ->float | int | str | None:  # noqa: D102
        if self.client_id in self.coordinator.data:
            return self.coordinator.\
                data[self.client_id][self.entity_description.key]
        return None

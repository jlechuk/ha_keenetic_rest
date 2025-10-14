# noqa: D100

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import BaseSensorDescription
from .router import KeeneticRouter


@callback
def add_network_client_sensors(
    router: KeeneticRouter,
    client_ids: list | set,
    sensor_descriptions: tuple,
    sensor_entity_class: type,
    async_add_entities: AddEntitiesCallback
) -> None:
    """Add Network clients sensors."""
    network_client_sensors = [
        sensor_entity_class(
            router,
            description,
            client_id
        ) for description in sensor_descriptions for client_id in client_ids
    ]
    async_add_entities(network_client_sensors)


class BaseSensor(CoordinatorEntity):
    """Base class for Keentic router and Network clients sensors."""
    entity_description: BaseSensorDescription
    _attr_has_entity_name = True

    def __init__(  # noqa: D107
        self,
        router: KeeneticRouter,
        entity_description: BaseSensorDescription
    ) -> None:
        coordinator = router.\
            update_coordinators[entity_description.update_coordinator]
        super().__init__(coordinator)

        self.router = router
        self.entity_description = entity_description


class NetworkClientBaseSensor(BaseSensor):
    """Base class for Network client sensor."""
    def __init__(  # noqa: D107
        self,
        router: KeeneticRouter,
        entity_description: BaseSensorDescription,
        client_id: str
    ) -> None:
        super().__init__(router, entity_description)
        self.client_id = client_id
        self._attr_unique_id = \
            f"{router.unique_id}-{client_id}-{entity_description.key}".lower()

    @property
    def extra_state_attributes(self) -> dict:  # noqa: D102
        attrs = {}
        attr_keys = self.entity_description.extra_attributes
        client_data = self.coordinator.data.get(self.client_id, None)
        if attr_keys and client_data:
            for attr_key in attr_keys:
                attrs[attr_key] = client_data.get(attr_key, None)
        return attrs

    @property
    def available(self) -> bool:  # noqa: D102
        return super().available and self.client_id in self.coordinator.data

    @property
    def device_info(self) -> DeviceInfo:
        """Network client device info."""
        return self.router.network_client_device_info(self.client_id)


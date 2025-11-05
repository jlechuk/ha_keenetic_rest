# noqa: D100

from typing import Any

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import BaseKeeneticEntityDescription
from .router import KeeneticRouter


class BaseKeeneticEntity(CoordinatorEntity):
    """Base class for all integration entities."""
    entity_description: BaseKeeneticEntityDescription
    _attr_has_entity_name = True

    def __init__(  # noqa: D107
        self,
        router: KeeneticRouter,
        entity_description: BaseKeeneticEntityDescription
    ) -> None:
        coordinator = router.\
            update_coordinators[entity_description.update_coordinator]
        super().__init__(coordinator)

        self.router = router
        self.entity_description = entity_description

    @property
    def native_value(self) -> float | int | str | None:  # noqa: D102
        return self._get_coordinator_data().get(self.entity_description.key)

    @property
    def available(self) -> bool:  # noqa: D102
        return super().available

    @property
    def extra_state_attributes(self) -> dict:  # noqa: D102
        attributes = {}
        attr_description = self.entity_description.extra_attributes
        data = self._get_attributes_data()
        if attr_description and data:
            for attr_name, attr_key in attr_description.items():
                attributes[attr_name] = \
                    self._extract_attribute_value(attr_key, data)
        return attributes

    def _get_coordinator_data(self) -> Any:
        raise NotImplementedError

    def _get_attributes_data(self) -> Any:
        return self._get_coordinator_data()

    @staticmethod
    def _extract_attribute_value(attr_key: dict | str, data: dict) -> Any:
        if data is None:
            return None

        if type(attr_key) is dict:
            key = next(iter(attr_key))
            return BaseKeeneticEntity._extract_attribute_value(attr_key[key],
                                                               data.get(key))
        elif type(attr_key) is str:  # noqa: RET505
            return data.get(attr_key)
        else:
            return None


class BaseKeeneticRouterEntity(BaseKeeneticEntity):
    """Base class for Router entities."""
    def __init__(  # noqa: D107
        self,
        router: KeeneticRouter,
        entity_description: BaseKeeneticEntityDescription
    ) -> None:
        super().__init__(router, entity_description)
        self._attr_unique_id = \
            f"{router.unique_id}-{entity_description.key}".lower()

    @property
    def device_info(self) -> DeviceInfo:
        """Router device info."""
        return self.router.router_device_info

    def _get_coordinator_data(self):
        return self.coordinator.data


class BaseKeeneticNetworkClientEntity(BaseKeeneticEntity):
    """Base class for Network client entities."""
    def __init__(  # noqa: D107
        self,
        router: KeeneticRouter,
        entity_description: BaseKeeneticEntityDescription,
        client_id: str
    ) -> None:
        super().__init__(router, entity_description)
        self.client_id = client_id
        self._attr_unique_id = \
            f"{router.unique_id}-{client_id}-{entity_description.key}".lower()

    @property
    def available(self) -> bool:  # noqa: D102
        return super().available and self.client_id in self.coordinator.data

    @property
    def device_info(self) -> DeviceInfo:
        """Network client device info."""
        return self.router.make_client_device_info(self.client_id)

    def _get_coordinator_data(self):
        return self.coordinator.data.get(self.client_id)


@callback
def add_network_client_entities(
    router: KeeneticRouter,
    client_ids: list | set,
    entity_descriptions: tuple[BaseKeeneticEntityDescription, ...],
    async_add_entities: AddEntitiesCallback
) -> None:
    """Add Network client entities."""
    network_client_sensors = [
        description.entity_class(
            router,
            description,
            client_id
        ) for description in entity_descriptions for client_id in client_ids
    ]
    async_add_entities(network_client_sensors)

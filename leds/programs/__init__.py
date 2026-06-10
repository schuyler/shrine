"""Program ABC, SegmentParams dataclass, and program registry."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class SegmentParams:
    col: list[list[int]]  # up to 3 RGB triples
    bri: int              # 0-255
    fx: int = 0
    sx: int = 128
    ix: int = 128
    pal: int = 0
    on: bool = True


class Program(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    def initial_state(self) -> dict:
        return {}

    @abstractmethod
    def render(self, pads, palette, clock_phase, state: dict) -> tuple[list[SegmentParams], dict]: ...


_registry: dict[str, Program] = {}


def register(cls):
    """Class decorator. Instantiates and registers by name."""
    instance = cls()
    _registry[instance.name] = instance
    return cls


def get_program(name: str) -> Program:
    return _registry[name]


def list_programs() -> list[str]:
    return list(_registry.keys())


# Import built-in programs to trigger registration.
from leds.programs import breathe as _breathe  # noqa: E402, F401
from leds.programs import chase as _chase  # noqa: E402, F401

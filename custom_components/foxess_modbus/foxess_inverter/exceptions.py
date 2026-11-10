"""Errors raised by this library."""


class FoxEssError(Exception):
    """Base class for the errors of this library."""


class UnsupportedInverterError(FoxEssError):
    """The inverter reports a model this library does not know."""

    def __init__(self, model_name: str) -> None:
        super().__init__(f"unsupported inverter model {model_name!r}")
        self.model_name = model_name

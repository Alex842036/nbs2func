"""Minecraft datapack and mcfunction output helpers."""

__all__ = [
    "BasicMcfunctionWriter",
    "CommandWriteResult",
    "CommandWriterConfig",
    "GeneratedBuildPlan",
    "GeneratedCommand",
    "GeneratedComment",
    "GeneratedBuildSection",
    "PlacedBlock",
    "write_mcfunction",
]


def __getattr__(name: str) -> object:
    if name in {
        "BasicMcfunctionWriter",
        "CommandWriteResult",
        "CommandWriterConfig",
        "write_mcfunction",
    }:
        from . import command_writer

        return getattr(command_writer, name)
    if name in {
        "GeneratedBuildPlan",
        "GeneratedCommand",
        "GeneratedComment",
        "GeneratedBuildSection",
        "PlacedBlock",
    }:
        from . import models

        return getattr(models, name)
    raise AttributeError(name)

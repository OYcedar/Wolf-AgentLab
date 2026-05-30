"""RPG Maker 引擎类型定义。"""

from typing import Literal


type EngineKind = Literal["mv", "mz", "wolf"]


__all__: list[str] = ["EngineKind"]

## rule modules return this instead of raising, expected biz failures stay distinct from bugs
from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class Ok(Generic[T]):
    data: T
    ok: bool = True


@dataclass(frozen=True, slots=True)
class Err:
    code: str
    message: str
    ok: bool = False


Result = Ok[T] | Err

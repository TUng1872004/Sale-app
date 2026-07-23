from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, Field


T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int = Field(ge=1)
    per_page: int = Field(ge=1, le=100)

    @property
    def pages(self) -> int:
        return max(1, (self.total + self.per_page - 1) // self.per_page)

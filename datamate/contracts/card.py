"""Data card: a short, prompt-sized summary of one business's canonical data, given to [C] and used by [C3]."""
from __future__ import annotations

from pydantic import BaseModel


class DataCard(BaseModel):
    industry: str | None = None
    date_min: str | None = None  # YYYY-MM-DD, first day with orders
    date_max: str | None = None
    tables: list[str] = []  # canonical tables present
    fields: list[str] = []  # "table.column" present with values
    extra_tables: dict[str, str] = {}  # name -> description
    product_groups: list[str] = []
    channels: list[str] = []
    payment_methods: list[str] = []
    customer_groups: list[str] = []
    units: list[str] = []
    employees: list[str] = []
    n_products: int = 0
    n_customers: int = 0

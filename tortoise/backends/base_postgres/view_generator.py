"""
PostgreSQL-specific view schema generation for Tortoise ORM.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from tortoise.backends.base.view_generator import BaseViewSchemaGenerator

if TYPE_CHECKING:
    from tortoise.backends.base.client import BaseDBAsyncClient


class PostgreSQLViewSchemaGenerator(BaseViewSchemaGenerator):
    """
    PostgreSQL-specific view schema generator.

    Uses PostgreSQL syntax with CREATE OR REPLACE VIEW.
    """

    DIALECT = "postgres"
    VIEW_CREATE_TEMPLATE = 'CREATE OR REPLACE VIEW "{view_name}" AS\n{query};'
    VIEW_DROP_TEMPLATE = 'DROP VIEW IF EXISTS "{view_name}" CASCADE;'

    def __init__(self, client: BaseDBAsyncClient) -> None:
        super().__init__(client)

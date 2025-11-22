"""
MySQL-specific view schema generation for Tortoise ORM.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from tortoise.backends.base.view_generator import BaseViewSchemaGenerator

if TYPE_CHECKING:
    from tortoise.backends.mysql.client import MySQLClient


class MySQLViewSchemaGenerator(BaseViewSchemaGenerator):
    """
    MySQL-specific view schema generator.

    Uses MySQL syntax with backticks for identifiers and CREATE OR REPLACE VIEW.
    """

    DIALECT = "mysql"
    VIEW_CREATE_TEMPLATE = "CREATE OR REPLACE VIEW `{view_name}` AS\n{query};"
    VIEW_DROP_TEMPLATE = "DROP VIEW IF EXISTS `{view_name}`;"

    def __init__(self, client: MySQLClient) -> None:
        super().__init__(client)
        self.client: MySQLClient = client

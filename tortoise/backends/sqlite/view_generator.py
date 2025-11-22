"""
SQLite-specific view schema generation for Tortoise ORM.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from tortoise.backends.base.view_generator import BaseViewSchemaGenerator

if TYPE_CHECKING:
    from tortoise.backends.sqlite.client import SqliteClient


class SQLiteViewSchemaGenerator(BaseViewSchemaGenerator):
    """
    SQLite-specific view schema generator.

    SQLite does not support CREATE OR REPLACE VIEW, so views must be dropped first.
    """

    DIALECT = "sqlite"
    VIEW_CREATE_TEMPLATE = 'CREATE VIEW {exists}"{view_name}" AS\n{query};'
    VIEW_DROP_TEMPLATE = 'DROP VIEW IF EXISTS "{view_name}";'

    def __init__(self, client: SqliteClient) -> None:
        super().__init__(client)
        self.client: SqliteClient = client

    def get_create_schema_sql(self, safe: bool = True) -> str:
        """
        Generate SQL for creating all views.

        For SQLite, if not in safe mode, we need to drop views first since
        CREATE OR REPLACE is not supported.

        Args:
            safe: If False, drop existing views first

        Returns:
            Complete SQL script for creating all views
        """
        views_to_create = self._get_views_to_create()

        if not views_to_create:
            return ""

        statements = []

        # If not in safe mode, drop views first
        if not safe:
            for view in views_to_create:
                view_name = view._meta.db_view
                if view._meta.schema:
                    view_name = f'"{view._meta.schema}"."{view_name}"'
                drop_sql = self.VIEW_DROP_TEMPLATE.format(view_name=view_name)
                statements.append(drop_sql)

        # Create views
        for view in views_to_create:
            view_sql = self._get_view_sql(view, safe)
            statements.append(view_sql)

        return "\n\n".join(statements)

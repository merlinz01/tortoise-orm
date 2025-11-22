"""
View schema generation for Tortoise ORM.

This module provides the base view schema generator for creating SQL views.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tortoise.backends.base.client import BaseDBAsyncClient
    from tortoise.views import View


class BaseViewSchemaGenerator:
    """
    Base class for generating SQL view schemas.

    Database-specific implementations should subclass this and override templates as needed.
    """

    DIALECT = "sql"
    VIEW_CREATE_TEMPLATE = 'CREATE VIEW {exists}"{view_name}" AS\n{query};'
    VIEW_DROP_TEMPLATE = 'DROP VIEW IF EXISTS "{view_name}";'

    def __init__(self, client: BaseDBAsyncClient) -> None:
        self.client = client

    def _get_views_to_create(self) -> list[type[View]]:
        """
        Get all views registered in Tortoise that should be created for this client.

        Returns:
            List of View classes to create
        """
        from tortoise import Tortoise

        views_to_create: list[type[View]] = []
        for app in Tortoise.apps.values():
            for model_or_view in app.values():
                # Check if this is a View (not a Model) and belongs to this client
                if hasattr(model_or_view, "_meta"):
                    meta = model_or_view._meta
                    # Views have a different meta type than models
                    if meta.__class__.__name__ == "ViewMetaInfo":
                        if hasattr(meta, "default_connection") and meta.default_connection:
                            # Check if view belongs to this client's connection
                            from tortoise.connection import connections

                            view_client = connections.get(meta.default_connection)
                            if view_client is self.client:
                                views_to_create.append(model_or_view)  # type: ignore
                        else:
                            # If no specific connection, include it
                            views_to_create.append(model_or_view)  # type: ignore

        return views_to_create

    def _get_view_sql(self, view: type[View], safe: bool = True) -> str:
        """
        Generate CREATE VIEW SQL for a single view.

        Args:
            view: The View class to generate SQL for
            safe: If True, use IF NOT EXISTS clause

        Returns:
            SQL CREATE VIEW statement
        """
        view_name = view._meta.db_view
        schema_prefix = ""
        if view._meta.schema:
            schema_prefix = f'"{view._meta.schema}".'
            view_name = f"{schema_prefix}{view_name}"

        # Generate the SELECT query
        from tortoise.views import ViewQueryGenerator

        query_generator = ViewQueryGenerator(view)
        select_query = query_generator.generate_select_query()

        # Indent the query for readability
        indented_query = "\n".join("    " + line for line in select_query.split("\n"))

        # Build CREATE VIEW statement
        exists = "IF NOT EXISTS " if safe else ""
        view_sql = self.VIEW_CREATE_TEMPLATE.format(
            exists=exists,
            view_name=view._meta.db_view,
            query=indented_query,
        )

        return view_sql

    def get_create_schema_sql(self, safe: bool = True) -> str:
        """
        Generate SQL for creating all views.

        Args:
            safe: If True, use IF NOT EXISTS clauses

        Returns:
            Complete SQL script for creating all views
        """
        views_to_create = self._get_views_to_create()

        if not views_to_create:
            return ""

        view_creation_strings = []
        for view in views_to_create:
            view_sql = self._get_view_sql(view, safe)
            view_creation_strings.append(view_sql)

        return "\n\n".join(view_creation_strings)

    def get_drop_schema_sql(self) -> str:
        """
        Generate SQL for dropping all views.

        Returns:
            Complete SQL script for dropping all views
        """
        views_to_drop = self._get_views_to_create()

        if not views_to_drop:
            return ""

        drop_statements = []
        for view in views_to_drop:
            view_name = view._meta.db_view
            if view._meta.schema:
                view_name = f'"{view._meta.schema}"."{view_name}"'
            drop_sql = self.VIEW_DROP_TEMPLATE.format(view_name=view_name)
            drop_statements.append(drop_sql)

        return "\n".join(drop_statements)

    async def generate_from_string(self, creation_string: str) -> None:
        """
        Execute the view creation SQL.

        Args:
            creation_string: SQL script to execute
        """
        if creation_string:
            await self.client.execute_script(creation_string)

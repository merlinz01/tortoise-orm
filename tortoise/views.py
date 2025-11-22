"""
SQL View support for Tortoise ORM.

This module provides the View base class for defining database views in a similar way to Models.
"""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING, Any

from tortoise.exceptions import ConfigurationError
from tortoise.fields.base import Field
from tortoise.queryset import QuerySet

if TYPE_CHECKING:
    from tortoise.models import Model
    from tortoise.queryset import ExistsQuery, QuerySetSingle

__all__ = ["View", "ViewMetaInfo", "ViewQueryGenerator"]


class ViewQueryGenerator:
    """
    Generates SQL SELECT statements for views based on field mappings.

    Handles join expressions like "customer__name" and field aliases.
    """

    def __init__(self, view_class: type[View]) -> None:
        self.view_class = view_class
        self.meta = view_class._meta

    def generate_select_query(self) -> str:
        """
        Generate the SELECT query for the view.

        Parses field source mappings and generates appropriate JOINs and column selections.

        Returns:
            SQL SELECT statement as a string
        """
        if not self.meta.source_model:
            raise ConfigurationError(
                f"View {self.view_class.__name__} must specify a source model in Meta.model"
            )

        source_model = self.meta.source_model
        source_table = source_model._meta.db_table
        schema_prefix = f'"{self.meta.schema}".' if self.meta.schema else ""

        # Parse field mappings to build SELECT columns and JOINs
        select_columns = []
        joins: dict[str, str] = {}  # Maps join path to JOIN clause
        join_aliases: dict[str, str] = {}  # Maps join path to table alias

        for field_name, source_expr in self.meta.field_source_map.items():
            if "__" in source_expr:
                # This is a join expression (e.g., "customer__name")
                column, alias = self._parse_join_expression(
                    source_expr, source_model, joins, join_aliases
                )
                select_columns.append(f'{column} AS "{field_name}"')
            else:
                # Simple column reference
                select_columns.append(f'"{source_table}"."{source_expr}" AS "{field_name}"')

        # Build the final query
        select_clause = ",\n    ".join(select_columns)
        from_clause = f'{schema_prefix}"{source_table}"'

        # Add JOIN clauses
        join_clause = ""
        if joins:
            sorted_joins = sorted(joins.items(), key=lambda x: len(x[0]))  # Sort by depth
            join_clause = "\n" + "\n".join(join[1] for join in sorted_joins)

        query = f"SELECT\n    {select_clause}\nFROM {from_clause}{join_clause}"  # nosec B608
        return query

    def _parse_join_expression(
        self,
        source_expr: str,
        source_model: type[Model],
        joins: dict[str, str],
        join_aliases: dict[str, str],
    ) -> tuple[str, str]:
        """
        Parse a join expression like "customer__name" and build the necessary JOIN clauses.

        Args:
            source_expr: The source expression (e.g., "customer__name")
            source_model: The source model for the view
            joins: Dictionary to populate with JOIN clauses
            join_aliases: Dictionary to populate with table aliases

        Returns:
            Tuple of (column_reference, table_alias)
        """
        parts = source_expr.split("__")
        current_model = source_model
        join_path = []
        schema_prefix = f'"{self.meta.schema}".' if self.meta.schema else ""

        # Navigate through the relationship chain
        for i, part in enumerate(parts[:-1]):  # All but the last part are relations
            join_path.append(part)
            path_key = "__".join(join_path)

            if path_key not in joins:
                # Get the field object for this relationship
                if part not in current_model._meta.fields_map:
                    raise ConfigurationError(
                        f"Field {part} not found in model {current_model.__name__}"
                    )

                field = current_model._meta.fields_map[part]

                # Check if it's a foreign key or one-to-one field
                if not hasattr(field, "related_model"):
                    raise ConfigurationError(
                        f"Field {part} in {current_model.__name__} is not a relational field"
                    )

                related_model = field.related_model
                related_table = related_model._meta.db_table
                join_alias = f"{related_table}_{len(joins)}"
                join_aliases[path_key] = join_alias

                # Build JOIN clause
                # For ForeignKey: current_table.field_id = related_table.id
                fk_column = field.source_field or f"{part}_id"
                related_pk = related_model._meta.db_pk_column

                if i == 0:
                    # First join is from the source table
                    left_table = f'"{source_model._meta.db_table}"'
                else:
                    # Subsequent joins are from the previous join alias
                    parent_path = "__".join(join_path[:-1])
                    left_table = f'"{join_aliases[parent_path]}"'

                join_clause = (
                    f'LEFT JOIN {schema_prefix}"{related_table}" AS "{join_alias}" '
                    f'ON {left_table}."{fk_column}" = "{join_alias}"."{related_pk}"'
                )
                joins[path_key] = join_clause

                current_model = related_model

        # The last part is the column name
        column_name = parts[-1]
        if len(parts) > 1:
            table_alias = join_aliases["__".join(parts[:-1])]
            column_ref = f'"{table_alias}"."{column_name}"'
        else:
            column_ref = f'"{source_model._meta.db_table}"."{column_name}"'

        return column_ref, table_alias if len(parts) > 1 else source_model._meta.db_table

    def _get_field_type(self, field: Field) -> str:
        """
        Get the SQL type for a field (for validation purposes).
        """
        # This is just for validation - the actual type comes from the view definition
        return getattr(field, "SQL_TYPE", "VARCHAR(255)")


class ViewMetaInfo:
    """
    Metadata container for View classes.

    Stores information about the view's fields, source model, and query generation.
    """

    __slots__ = (
        "view_name",
        "schema",
        "app",
        "fields",
        "fields_map",
        "field_source_map",  # Maps field name to source column (e.g., "customer__name")
        "source_model",
        "default_connection",
        "_model",
        "_inited",
        "manager",
        "view_description",
        "basetable",
        "basequery",
        "basequery_all_fields",
        "db_fields",
        "ordering",
        "fields_db_projection",
        "fields_db_projection_reverse",
        "db_native_fields",
        "pk_attr",
        "db_pk_column",
        "generated_db_fields",
        "fk_fields",
        "o2o_fields",
        "m2m_fields",
        "backward_fk_fields",
        "backward_o2o_fields",
        "fetch_fields",
        "filters",
        "_filters",
    )

    def __init__(self, meta: View.Meta) -> None:
        self.view_name: str = getattr(meta, "table", "")
        self.schema: str | None = getattr(meta, "schema", None)
        self.app: str | None = getattr(meta, "app", None)
        self.source_model: type[Model] | None = getattr(meta, "model", None)
        self.view_description: str = getattr(meta, "view_description", "")

        self.fields: set[str] = set()
        self.fields_map: dict[str, Field] = {}
        self.field_source_map: dict[str, str] = {}  # Maps field name -> source expression

        self._inited: bool = False
        self.default_connection: str | None = None
        self._model: type[View] = None  # type: ignore
        self.manager: Any = None  # Views use a read-only manager

        # Query-related attributes (set later during initialization)
        self.basetable: Any = None
        self.basequery: Any = None
        self.basequery_all_fields: Any = None
        self.db_fields: list[str] = []
        self.ordering: list[str] = []  # Views don't have default ordering

        # Field projection mappings (field_name -> db_column_name)
        self.fields_db_projection: dict[str, str] = {}
        self.fields_db_projection_reverse: dict[str, str] = {}
        self.db_native_fields: list[tuple[str, str, Any]] = []
        self.pk_attr: str = ""  # Views typically don't have a PK
        self.db_pk_column: str = ""  # Views typically don't have a PK column
        self.generated_db_fields: Any = None  # Views don't have generated fields

        # Relationship fields (views don't have relationships, but querysets check for them)
        self.fk_fields: set[str] = set()
        self.o2o_fields: set[str] = set()
        self.m2m_fields: set[str] = set()
        self.backward_fk_fields: set[str] = set()
        self.backward_o2o_fields: set[str] = set()
        self.fetch_fields: set[str] = set()
        self.filters: dict = {}
        self._filters: dict = {}

    @property
    def db(self) -> Any:
        """Returns the database client for this view."""
        from tortoise.connection import connections

        if self.default_connection:
            return connections.get(self.default_connection)
        return connections.get("default")

    @property
    def full_name(self) -> str:
        """Returns the full name of the view in 'app.ViewName' format."""
        if self.app:
            return f"{self.app}.{self._model.__name__}"
        return self._model.__name__

    @property
    def db_view(self) -> str:
        """Returns the database view name."""
        if not self.view_name:
            return self._model.__name__.lower()
        return self.view_name

    @property
    def db_table(self) -> str:
        """Alias for db_view - views use the same property name as models for compatibility."""
        return self.db_view

    def get_filter(self, key: str) -> Any:
        """Get a filter by key."""
        return self.filters[key]

    def finalise_fields(self) -> None:
        """
        Finalizes the fields for the view after all fields have been parsed.
        """
        from tortoise.filters import get_filters_for_field

        # Build the fields_db_projection mapping (field_name -> db_column_name)
        # For views, the field name IS the column name in the view
        self.fields_db_projection = {
            field_name: field_name for field_name in self.fields_map.keys()
        }
        self.fields_db_projection_reverse = {v: k for k, v in self.fields_db_projection.items()}

        # Generate filters for each field
        filters = {}
        for field_name, field in self.fields_map.items():
            filters.update(
                get_filters_for_field(
                    field_name=field_name,
                    field=field,
                    source_field=field_name,  # For views, field name is the DB column name
                )
            )
        self.filters = filters
        self._filters = filters

        self._inited = True


class ViewMeta(type):
    """
    Metaclass for View.

    Handles parsing of field definitions and metadata when a View class is created.
    """

    __slots__ = ()

    def __new__(cls, name: str, bases: tuple[type, ...], attrs: dict[str, Any]) -> ViewMeta:
        meta_class: View.Meta = attrs.get("Meta", type("Meta", (), {}))

        # Parse fields
        fields_map: dict[str, Field] = {}
        field_source_map: dict[str, str] = {}

        # Search for Field instances in the class attributes
        for base in bases:
            cls._search_for_field_attributes(base, fields_map, field_source_map)

        # Process current class fields
        for key, value in list(attrs.items()):
            if isinstance(value, Field):
                fields_map[key] = value
                # Get the source column from the field's source_field or use the field name
                source = value.source_field if value.source_field else key
                field_source_map[key] = source

        # Build metadata
        attrs["_meta"] = meta = cls.build_meta(meta_class, fields_map, field_source_map)

        # Clean up field definitions from class dict
        for field_name in fields_map:
            attrs.pop(field_name, None)

        # Create the new class
        new_class = super().__new__(cls, name, bases, attrs)

        # Set the model reference on fields
        for field in meta.fields_map.values():
            field.model = new_class  # type: ignore

        # Set the model reference on meta
        meta._model = new_class  # type: ignore

        # Parse docstrings
        if new_class.__doc__ and not meta.view_description:
            meta.view_description = inspect.cleandoc(new_class.__doc__).split("\n")[0]

        meta.finalise_fields()

        return new_class

    @classmethod
    def _search_for_field_attributes(
        cls, base: type, fields_map: dict[str, Field], field_source_map: dict[str, str]
    ) -> None:
        """
        Search for Field attributes in base classes.
        """
        for parent in base.__mro__[1:]:
            cls._search_for_field_attributes(parent, fields_map, field_source_map)

        if meta := getattr(base, "_meta", None):
            if isinstance(meta, ViewMetaInfo):
                for key, value in meta.fields_map.items():
                    if key not in fields_map:
                        fields_map[key] = value
                        field_source_map[key] = meta.field_source_map.get(key, key)
        else:
            # Check for mixin fields
            for key, value in base.__dict__.items():
                if isinstance(value, Field) and key not in fields_map:
                    fields_map[key] = value
                    source = value.source_field if value.source_field else key
                    field_source_map[key] = source

    @staticmethod
    def build_meta(
        meta_class: View.Meta,
        fields_map: dict[str, Field],
        field_source_map: dict[str, str],
    ) -> ViewMetaInfo:
        """
        Build the ViewMetaInfo instance for this view.
        """
        meta = ViewMetaInfo(meta_class)
        meta.fields_map = fields_map
        meta.field_source_map = field_source_map
        meta.fields = set(fields_map.keys())
        return meta


class ViewQuerySet(QuerySet):
    """
    QuerySet for Views - read-only version that doesn't support mutations.
    Views don't have create/update/delete/bulk_create methods.
    """

    def __init__(self, model: type[View]) -> None:
        super().__init__(model)


class View(metaclass=ViewMeta):
    """
    Base class for database views.

    Views are similar to Models but are read-only and backed by a SQL view instead of a table.

    Example:
        ```python
        from tortoise import fields
        from tortoise.models import Model
        from tortoise.views import View


        class Order(Model):
            id = fields.IntField(primary_key=True)
            customer: fields.ForeignKeyRelation[Customer] = fields.ForeignKeyField(
                "models.Customer",
                related_name="orders",
            )
            total = fields.DecimalField(max_digits=10, decimal_places=2)


        class OrderSummary(View):
            # Map view columns to fields
            order_id = fields.IntField(source_field="id")
            customer_name = fields.CharField(source_field="customer__name", max_length=255)
            order_total = fields.DecimalField(source_field="total", max_digits=10, decimal_places=2)

            class Meta:
                table = "order_summary"
                model = Order  # Source model for the view
        ```
    """

    # Will be populated by metaclass
    _meta = ViewMetaInfo(None)  # type: ignore

    class Meta:
        """
        Metadata for the View.

        Attributes:
            table: The name of the database view (optional, defaults to class name in lowercase)
            model: The source Model class for this view (optional, for automatic query generation)
            schema: The database schema name (optional)
            app: The app name for this view (optional)
            view_description: Description of the view (optional)
        """

    def __init__(self, **kwargs: Any) -> None:
        """
        Initialize a View instance.

        Views are read-only, so they can only be queried, not saved or deleted.
        """
        meta = self._meta

        # Set field values from kwargs
        for key, value in kwargs.items():
            if key in meta.fields_map:
                setattr(self, key, value)
            else:
                raise ValueError(f"Unknown field: {key}")

    def __str__(self) -> str:
        return f"<{self.__class__.__name__}>"

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}: {self._meta.db_view}>"

    def __hash__(self) -> int:
        return hash(str(self))

    def __eq__(self, other: Any) -> bool:
        if type(self) is not type(other):
            return False
        return hash(self) == hash(other)

    @classmethod
    def _init_from_db(cls, **kwargs: Any) -> View:
        """
        Create a View instance from database results.
        """
        instance = cls.__new__(cls)
        # Set field values directly instead of calling __init__
        for key, value in kwargs.items():
            setattr(instance, key, value)
        return instance

    @classmethod
    def all(cls) -> ViewQuerySet:
        """
        Returns a QuerySet for all records in the view.
        """
        return ViewQuerySet(cls)

    @classmethod
    def filter(cls, *args: Any, **kwargs: Any) -> QuerySet[Any]:
        """
        Returns a filtered QuerySet for the view.
        """
        return ViewQuerySet(cls).filter(*args, **kwargs)

    @classmethod
    def get(cls, *args: Any, **kwargs: Any) -> QuerySetSingle[Any]:
        """
        Returns a single record from the view matching the query.
        """
        return ViewQuerySet(cls).get(*args, **kwargs)

    @classmethod
    def first(cls) -> QuerySetSingle[Any | None]:
        """
        Returns the first record from the view.
        """
        return ViewQuerySet(cls).first()

    @classmethod
    def exists(cls, *args: Any, **kwargs: Any) -> ExistsQuery:
        """
        Returns whether records exist in the view matching the query.
        """
        return ViewQuerySet(cls).filter(*args, **kwargs).exists()

    # Views don't have save/create/delete/fetch_related methods - they are read-only

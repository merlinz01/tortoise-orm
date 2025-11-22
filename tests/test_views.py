"""
Tests for SQL View support in Tortoise ORM.
"""

import pytest

from tortoise import Tortoise, fields
from tortoise.models import Model
from tortoise.views import View


class Customer(Model):
    id = fields.IntField(primary_key=True)
    name = fields.CharField(max_length=255)

    class Meta:
        table = "customer"


class Order(Model):
    id = fields.IntField(primary_key=True)
    customer: fields.ForeignKeyRelation[Customer] = fields.ForeignKeyField(
        "models.Customer", related_name="orders", on_delete=fields.OnDelete.CASCADE
    )
    total = fields.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        table = "order"


class CustomerOrders(View):
    """View combining customer and order data."""

    order_id = fields.IntField(source_field="id")
    customer_id = fields.IntField(source_field="customer__id")
    customer_name = fields.CharField(source_field="customer__name", max_length=255)
    order_total = fields.DecimalField(source_field="total", max_digits=10, decimal_places=2)

    class Meta:
        table = "customer_orders"
        model = Order


@pytest.mark.asyncio
async def test_view_import():
    """Test that View can be imported."""
    from tortoise import View as ImportedView

    assert ImportedView is View


@pytest.mark.asyncio
async def test_view_meta_info():
    """Test that View has correct metadata."""
    assert CustomerOrders._meta.db_view == "customer_orders"
    assert CustomerOrders._meta.source_model is Order
    assert "order_id" in CustomerOrders._meta.fields_map
    assert "customer_name" in CustomerOrders._meta.fields_map


@pytest.mark.asyncio
async def test_view_field_mappings():
    """Test that field mappings are correct."""
    assert CustomerOrders._meta.field_source_map["order_id"] == "id"
    assert CustomerOrders._meta.field_source_map["customer_id"] == "customer__id"
    assert CustomerOrders._meta.field_source_map["customer_name"] == "customer__name"
    assert CustomerOrders._meta.field_source_map["order_total"] == "total"


@pytest.mark.asyncio
async def test_view_sql_generation():
    """Test that view SQL is generated correctly."""
    from tortoise.connection import connections
    from tortoise.utils import get_view_schema_sql

    await Tortoise.init(db_url="sqlite://:memory:", modules={"models": [__name__]})
    await Tortoise.generate_schemas()

    client = connections.get("default")
    view_sql = get_view_schema_sql(client, safe=True)

    assert "CREATE VIEW" in view_sql
    assert "customer_orders" in view_sql
    assert "SELECT" in view_sql
    # Should have joins for the customer table
    assert "LEFT JOIN" in view_sql or "JOIN" in view_sql

    await Tortoise._drop_databases()


@pytest.mark.asyncio
async def test_view_querying():
    """Test that we can query data from a view."""
    await Tortoise.init(db_url="sqlite://:memory:", modules={"models": [__name__]})
    await Tortoise.generate_schemas()

    # Create test data
    customer1 = await Customer.create(id=1, name="Alice")
    customer2 = await Customer.create(id=2, name="Bob")

    await Order.create(id=1, customer=customer1, total=100.50)
    await Order.create(id=2, customer=customer1, total=75.25)
    await Order.create(id=3, customer=customer2, total=200.00)

    # Query the view
    results = await CustomerOrders.all()
    assert len(results) == 3

    # Check first result
    first = results[0]
    assert first.order_id == 1
    assert first.customer_id == 1
    assert first.customer_name == "Alice"
    assert float(first.order_total) == 100.50

    # Filter by customer
    alice_orders = await CustomerOrders.filter(customer_name="Alice")
    assert len(alice_orders) == 2

    bob_orders = await CustomerOrders.filter(customer_name="Bob")
    assert len(bob_orders) == 1
    assert bob_orders[0].customer_id == 2

    await Tortoise._drop_databases()


@pytest.mark.asyncio
async def test_view_readonly():
    """Test that views are read-only - they don't have create/save/delete methods."""
    await Tortoise.init(db_url="sqlite://:memory:", modules={"models": [__name__]})
    await Tortoise.generate_schemas()

    # Create test data
    customer = await Customer.create(id=1, name="Test")
    await Order.create(id=1, customer=customer, total=50.00)

    # Views don't have create/save/delete methods
    assert not hasattr(CustomerOrders, "create")

    result = await CustomerOrders.first()
    assert not hasattr(result, "save")
    assert not hasattr(result, "delete")
    assert not hasattr(result, "fetch_related")

    await Tortoise._drop_databases()

from django.db import models
from django.contrib.auth.models import User

class WarehouseModel(models.Model):
    name = models.CharField(max_length=100)
    location = models.CharField(max_length=255)
    size = models.CharField(max_length=50)

    def __str__(self):
        return self.name
    
class WarehouseGridModel(models.Model):
    warehouse = models.ForeignKey(WarehouseModel, on_delete=models.CASCADE, related_name='warehouse_grid')
    rows = models.PositiveIntegerField(default=0)
    columns = models.PositiveIntegerField(default=0)

class ShelfModel(models.Model):
    identifier = models.CharField(max_length=50)
    max_volume = models.FloatField(default=0)
    max_weight = models.FloatField(default=0)
    row = models.PositiveIntegerField(null=True)
    column = models.PositiveIntegerField(null=True)
    grid = models.ForeignKey(WarehouseGridModel, on_delete=models.CASCADE, related_name='shelves')
    is_active = models.BooleanField(default=False)

    def __str__(self):
        return f"Shelf {self.identifier} in {self.grid.warehouse.name}"

class LevelModel(models.Model):
    shelf = models.ForeignKey(ShelfModel, on_delete=models.CASCADE, related_name='levels')
    floor_number = models.PositiveIntegerField()
    max_volume = models.FloatField()
    max_weight = models.FloatField()

    class Meta:
        unique_together = ('shelf', 'floor_number')

    def __str__(self):
        return f"Level {self.floor_number} of {self.shelf.identifier}"

class ProductTypeModel(models.Model):
    name = models.CharField(max_length=100)
    codigo = models.CharField(max_length=100, blank=True, null=True)

    def __str__(self):
        return self.name

class SupplierModel(models.Model):
    name = models.CharField(max_length=100)
    contact_info = models.CharField(max_length=255)

    def __str__(self):
        return self.name

class InventoryItemModel(models.Model):
    level = models.ForeignKey(LevelModel, on_delete=models.CASCADE, related_name='items')
    product_type = models.ForeignKey(ProductTypeModel, on_delete=models.CASCADE)  # Tipo de producto
    supplier = models.ForeignKey(SupplierModel, on_delete=models.CASCADE, related_name='inventory_items')
    product_name = models.CharField(max_length=100)
    quantity = models.PositiveIntegerField()
    weight = models.FloatField(blank=True, null=True)
    volume = models.FloatField(blank=True, null=True)
    received_date = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.product_name} - {self.quantity} unidades"

class MovementModel(models.Model):
    MOVEMENT_TYPES = [
        ('IN', 'Entrada'),
        ('OUT', 'Salida'),
        ('TRANSFER', 'Transferencia'),
    ]

    item = models.ForeignKey(InventoryItemModel, on_delete=models.CASCADE, related_name='movements')
    movement_type = models.CharField(max_length=10, choices=MOVEMENT_TYPES)
    quantity = models.PositiveIntegerField()
    timestamp = models.DateTimeField(auto_now_add=True)
    performed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    source_warehouse = models.ForeignKey(WarehouseModel, on_delete=models.SET_NULL, null=True, blank=True, related_name='source_movements')
    destination_warehouse = models.ForeignKey(WarehouseModel, on_delete=models.SET_NULL, null=True, blank=True, related_name='destination_movements')

    def __str__(self):
        return f"{self.get_movement_type_display()} - {self.quantity} unidades de {self.item.product_name}"

class MovementInModel(models.Model):
    supplier = models.ForeignKey(SupplierModel, on_delete=models.CASCADE)
    warehouse = models.ForeignKey(WarehouseModel, on_delete=models.CASCADE, blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    performed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    status = models.CharField(max_length=20, choices=[
        ('PENDING', 'Pendiente de distribución'),
        ('DISTRIBUTED', 'Distribuido'),
    ], default='PENDING')
    distributed_timestamp = models.DateTimeField(null=True, blank=True)

class MovementInItemModel(models.Model):
    movement = models.ForeignKey(MovementInModel, on_delete=models.CASCADE, related_name='items')
    product_type = models.ForeignKey(ProductTypeModel, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField()
    weight = models.FloatField(null=True, blank=True)
    volume = models.FloatField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True, blank=True, null=True)
    
class MovementInDistributionModel(models.Model):
    movement_item = models.ForeignKey(MovementInItemModel, on_delete=models.CASCADE)
    level = models.ForeignKey(LevelModel, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField()
    weight = models.FloatField(null=True, blank=True)
    volume = models.FloatField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True, blank=True, null=True)

class InternalMovementModel(models.Model):
    item = models.ForeignKey('InventoryItemModel', on_delete=models.CASCADE)
    source_level = models.ForeignKey('LevelModel', on_delete=models.CASCADE, related_name='source_movements')
    destination_level = models.ForeignKey('LevelModel', on_delete=models.CASCADE, related_name='destination_movements')
    quantity = models.IntegerField()
    timestamp = models.DateTimeField(auto_now_add=True)
    performed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    
    # Agregar campos para mantener información del origen
    source_shelf_identifier = models.CharField(max_length=50, blank=True, null=True)  # Nuevo campo
    source_level_number = models.IntegerField(blank=True, null=True)  # Nuevo campo

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"Transferencia de {self.quantity} unidades de {self.source_level} a {self.destination_level}"

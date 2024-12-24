from django.shortcuts import render, get_object_or_404, redirect
from .models import WarehouseModel, ShelfModel, LevelModel, InventoryItemModel, MovementModel, ProductTypeModel, SupplierModel, WarehouseGridModel, MovementInModel, MovementInItemModel, MovementInDistributionModel, InternalMovementModel
from .forms import InventoryItemForm, MovementForm
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
import json
import logging
from django.db import models
from django.contrib import messages
from django.utils import timezone

# Configura el logger
logger = logging.getLogger(__name__)

def dashboard(request):
    warehouses = WarehouseModel.objects.all()
    return render(request, 'nave/dashboard.html', {'warehouses': warehouses})

def registerWarehouse(request):
    if request.method == 'POST':
        try:
            name = request.POST.get('name')
            location = request.POST.get('location')
            size = request.POST.get('size')
            rows = int(request.POST.get('rows', 0))
            columns = int(request.POST.get('columns', 0))
            
            # Crear el almacén
            warehouse = WarehouseModel.objects.create(
                name=name, 
                location=location, 
                size=size
            )
            
            # Crear la cuadrícula del almacén
            grid = WarehouseGridModel.objects.create(
                warehouse=warehouse,
                rows=rows,
                columns=columns
            )
            
            # Crear estantes inactivos en la cuadrícula
            for row in range(rows):
                for column in range(columns):
                    row_letter = chr(65 + row)
                    shelf = ShelfModel.objects.create(
                        identifier=f"Estante {row_letter}.{column + 1}",
                        row=row,
                        column=column,
                        grid=grid,
                        is_active=False
                    )
                    # Crear 3 niveles por defecto para cada estante
                    for floor_number in range(1, 4):  # 3 niveles
                        LevelModel.objects.create(
                            shelf=shelf,
                            floor_number=floor_number,
                            max_volume=0,  # Puedes ajustar estos valores según sea necesario
                            max_weight=0   # Puedes ajustar estos valores según sea necesario
                        )
            
            message = "Almacén registrado correctamente"
        except Exception as e:
            message = f"Error al registrar el almacén: {str(e)}"
        return render(request, 'nave/register_warehouse.html', {'message': message})
    return render(request, 'nave/register_warehouse.html')

def warehouse_detail(request, warehouse_id):
    warehouse = get_object_or_404(WarehouseModel, id=warehouse_id)
    grid = get_object_or_404(WarehouseGridModel, warehouse=warehouse)
    shelves = ShelfModel.objects.filter(grid=grid)

    # Obtener items regulares con su ubicación
    inventory_items = (
        InventoryItemModel.objects
        .filter(level__shelf__grid=grid)
        .select_related('level')  # Asegúrate de incluir el nivel para acceder a la ubicación
        .values('product_type__name', 'product_type__codigo', 'supplier__name', 'level__shelf__identifier', 'level__floor_number')  # Agregar ubicación
        .annotate(
            quantity=models.Sum('quantity'),
            weight=models.Sum('weight'),
            volume=models.Sum('volume'),
            product_name=models.F('product_type__name'),
            last_received=models.Max('received_date')
        )
    )

    # Obtener items distribuidos
    distributed_items = (
        MovementInDistributionModel.objects
        .filter(level__shelf__grid=grid)
        .values('movement_item__product_type__name', 'movement_item__product_type__codigo')
        .annotate(
            quantity=models.Sum('quantity'),
            weight=models.Sum('weight'),
            volume=models.Sum('volume'),
            product_name=models.F('movement_item__product_type__name'),
            supplier_name=models.F('movement_item__movement__supplier__name'),
            last_received=models.Max('timestamp')
        )
    )

    # Obtener recepciones pendientes
    pending_receptions = (
        MovementInModel.objects
        .filter(warehouse=warehouse, status='PENDING')
        .select_related('supplier')
        .prefetch_related('items__product_type')
    )

    # Calcular totales
    total_quantity = (
        sum(item['quantity'] for item in inventory_items) + 
        sum(item['quantity'] for item in distributed_items)
    )
    total_weight = (
        sum(item['weight'] for item in inventory_items if item['weight']) + 
        sum(item['weight'] for item in distributed_items if item['weight'])
    )
    total_volume = (
        sum(item['volume'] for item in inventory_items if item['volume']) + 
        sum(item['volume'] for item in distributed_items if item['volume'])
    )

    # Agregar análisis de ocupación de estantes
    shelf_occupancy = []
    active_shelves = ShelfModel.objects.filter(grid=grid, is_active=True)
    
    for shelf in active_shelves:
        # Calcular totales por estante
        regular_items = (InventoryItemModel.objects
            .filter(level__shelf=shelf)
            .aggregate(
                total_items=models.Sum('quantity'),
                total_weight=models.Sum('weight'),
                total_volume=models.Sum('volume')
            ))
            
        distributed_items = (MovementInDistributionModel.objects
            .filter(level__shelf=shelf)
            .aggregate(
                total_items=models.Sum('quantity'),
                total_weight=models.Sum('weight'),
                total_volume=models.Sum('volume')
            ))
            
        # Calcular totales combinados
        total_items = (regular_items['total_items'] or 0) + (distributed_items['total_items'] or 0)
        total_weight = (regular_items['total_weight'] or 0) + (distributed_items['total_weight'] or 0)
        total_volume = (regular_items['total_volume'] or 0) + (distributed_items['total_volume'] or 0)
        
        # Calcular porcentaje de ocupación (basado en el peso)
        max_weight_capacity = shelf.max_weight if shelf.max_weight > 0 else 1
        occupancy_percentage = (total_weight / max_weight_capacity * 100) if max_weight_capacity else 0
        
        # Determinar el estado de ocupación
        if occupancy_percentage == 0:
            status = 'empty'
        elif occupancy_percentage < 50:
            status = 'low'
        elif occupancy_percentage < 80:
            status = 'medium'
        else:
            status = 'high'

        shelf_occupancy.append({
            'shelf': shelf,
            'total_items': total_items,
            'total_weight': total_weight,
            'total_volume': total_volume,
            'occupancy_percentage': occupancy_percentage,
            'status': status,
            'levels_count': shelf.levels.count()
        })
    
    # Ordenar por disponibilidad (menos ocupados primero)
    shelf_occupancy.sort(key=lambda x: x['occupancy_percentage'])

    return render(request, 'nave/warehouse_detail.html', {
        'warehouse': warehouse,
        'grid': grid,
        'rows': range(grid.rows),
        'columns': range(grid.columns),
        'shelves': shelves,
        'inventory_items': inventory_items,
        'distributed_items': distributed_items,
        'pending_receptions': pending_receptions,
        'total_quantity': total_quantity,
        'total_weight': total_weight,
        'total_volume': total_volume,
        'shelf_occupancy': shelf_occupancy,
    })

def shelf_info(request, shelf_id):
    shelf = get_object_or_404(ShelfModel, id=shelf_id)
    levels = LevelModel.objects.filter(shelf=shelf)
    levels_info = []

    for level in levels:
        # Obtener items regulares con su información de origen
        regular_items = InventoryItemModel.objects.filter(level=level).select_related('product_type')
        for item in regular_items:
            # Buscar el último movimiento interno que llevó el item a este nivel
            internal_movement = InternalMovementModel.objects.filter(
                destination_level=level,
                item=item
            ).order_by('-timestamp').first()
            item.internal_movement = internal_movement

        # Obtener items distribuidos con su información de origen
        distributed_items = MovementInDistributionModel.objects.filter(
            level=level
        ).select_related('movement_item__product_type')
        for dist in distributed_items:
            # Buscar el último movimiento interno que llevó el item a este nivel
            internal_movement = InternalMovementModel.objects.filter(
                destination_level=level,
                item__product_type=dist.movement_item.product_type
            ).order_by('-timestamp').first()
            dist.internal_movement = internal_movement

        levels_info.append({
            'level': level,
            'regular_items': regular_items,
            'distributed_items': distributed_items,
        })

    context = {
        'shelf': shelf,
        'levels_info': levels_info,
    }
    return render(request, 'nave/shelf_info.html', context)

def configure_warehouse(request, warehouse_id):
    warehouse = get_object_or_404(WarehouseModel, id=warehouse_id)
    grid = get_object_or_404(WarehouseGridModel, warehouse=warehouse)
    shelves = ShelfModel.objects.filter(grid=grid)

    if request.method == 'POST':
        try:
            action = request.POST.get('action')
            
            if action == 'update_grid':
                new_rows = int(request.POST.get('rows', 0))
                new_columns = int(request.POST.get('columns', 0))
                
                # Validar que las nuevas dimensiones no sean menores que las posiciones ocupadas
                max_active_row = shelves.filter(is_active=True).aggregate(models.Max('row'))['row__max'] or -1
                max_active_column = shelves.filter(is_active=True).aggregate(models.Max('column'))['column__max'] or -1
                
                if new_rows <= max_active_row or new_columns <= max_active_column:
                    raise ValueError("No se pueden reducir las dimensiones por debajo de las posiciones ocupadas")
                
                # Actualizar dimensiones de la cuadrícula
                grid.rows = new_rows
                grid.columns = new_columns
                grid.save()
                
                # Crear nuevos estantes solo para las posiciones que no existen
                for row in range(new_rows):
                    for column in range(new_columns):
                        if not shelves.filter(row=row, column=column).exists():
                            row_letter = chr(65 + row)
                            ShelfModel.objects.create(
                                identifier=f"Estante {row_letter}.{column + 1}",
                                row=row,
                                column=column,
                                grid=grid,
                                is_active=False
                            )
                
                return redirect('configure_warehouse', warehouse_id=warehouse.id)
            
            row = int(request.POST.get('row'))
            column = int(request.POST.get('column'))
            action = request.POST.get('action')
            identifier = request.POST.get('identifier', '')  # Obtener el identificador
            
            shelf = ShelfModel.objects.filter(grid=grid, row=row, column=column).first()
            
            if action == 'toggle':
                if shelf:
                    # Cambiar el estado del estante
                    shelf.is_active = not shelf.is_active
                    if shelf.is_active:
                        shelf.identifier = identifier  # Actualizar el identificador si se activa
                    shelf.save()
                else:
                    # Crear nuevo estante si no existe
                    ShelfModel.objects.create(
                        grid=grid,
                        row=row,
                        column=column,
                        identifier=identifier,
                        is_active=True
                    )
            elif action == 'update':  # Nueva acción para actualizar
                if shelf:
                    shelf.identifier = identifier  # Actualizar el identificador
                    shelf.save()

            # Redirigir a la misma vista para refrescar la información
            return redirect('configure_warehouse', warehouse_id=warehouse.id)

        except Exception as e:
            return render(request, 'nave/configure_warehouse.html', {
                'warehouse': warehouse,
                'rows': range(grid.rows),
                'columns': range(grid.columns),
                'shelves': shelves,
                'message': f"Error al modificar el estante: {str(e)}"
            })

    # Actualizar shelves después de los cambios
    shelves = ShelfModel.objects.filter(grid=grid)
    return render(request, 'nave/configure_warehouse.html', {
        'warehouse': warehouse,
        'rows': range(grid.rows),
        'columns': range(grid.columns),
        'shelves': shelves
    })

def add_inventory_item(request, level_id):
    level = get_object_or_404(LevelModel, id=level_id)
    if request.method == 'POST':
        form = InventoryItemForm(request.POST)
        if form.is_valid():
            inventory_item = form.save(commit=False)
            inventory_item.level = level
            inventory_item.save()
            return redirect('level_detail', level_id=level.id)
    else:
        form = InventoryItemForm()
    return render(request, 'nave/add_inventory_item.html', {'form': form, 'level': level})

def add_supplier(request):
    if request.method == 'POST':
        try:
            name = request.POST.get('name')
            contact_info = request.POST.get('contact_info')
            SupplierModel.objects.create(name=name, contact_info=contact_info)
            message = f"El provedor {name} ha sido agregado correctamente"
            return render(request, 'nave/add_supplier.html', {'message': message})
        except Exception as e:
            message = f"Error al agregar el provedor: {str(e)}"
            return render(request, 'nave/add_supplier.html', {'message': message})
    return render(request, 'nave/add_supplier.html')

def add_product_type(request):
    if request.method == 'POST':
        try:
            name = request.POST.get('name')
            codigo = request.POST.get('codigo')
            message = f"El producto {name} con código {codigo} ha sido agregado correctamente"
            ProductTypeModel.objects.create(name=name, codigo=codigo)
            return render(request, 'nave/add_product_type.html', {'message': message})
        except Exception as e:
            message = f"Error al agregar el tipo de producto: {str(e)}"
            return render(request, 'nave/add_product_type.html', {'message': message})
    return render(request, 'nave/add_product_type.html')


def record_movement_in(request):
    if request.method == 'POST':
        try:
            # Crear el movimiento de entrada
            warehouse_id = request.POST.get('warehouse')
            warehouse = get_object_or_404(WarehouseModel, id=warehouse_id)
            supplier_id = request.POST.get('supplier')
            supplier = get_object_or_404(SupplierModel, id=supplier_id)
            
            movement = MovementInModel.objects.create(
                supplier=supplier,
                warehouse=warehouse,
                status='PENDING'
            )
            
            # Obtener todos los product_types del POST
            product_types = request.POST.getlist('product_type')
            quantities = request.POST.getlist('quantity')
            weights = request.POST.getlist('weight')
            volumes = request.POST.getlist('volume')
            
            # Crear un MovementInItemModel para cada producto
            detalles_productos = []
            for i in range(len(product_types)):
                MovementInItemModel.objects.create(
                    movement=movement,
                    product_type_id=product_types[i],
                    quantity=int(quantities[i]),
                    weight=weights[i] if weights[i] else None,
                    volume=volumes[i] if volumes[i] else None
                )
                detalles_productos.append(f"Producto: {product_types[i]}, Cantidad: {quantities[i]}, Peso: {weights[i] if weights[i] else 'N/A'}, Volumen: {volumes[i] if volumes[i] else 'N/A'}, Almacen: {warehouse.name}")
            
            mensaje_detalles = "Recepción registrada exitosamente con los siguientes detalles:\n" + "\n".join(detalles_productos)
            messages.success(request, mensaje_detalles)
            
            # Renderizar la misma plantilla con el mensaje
            context = {
                'warehouses': WarehouseModel.objects.all(),
                'suppliers': SupplierModel.objects.all(),
                'product_types': ProductTypeModel.objects.all(),
                'messages': messages.get_messages(request)  # Pasar los mensajes al contexto
            }
            return render(request, 'nave/record_movement_in.html', context)
        except Exception as e:
            messages.error(request, f"Error al registrar la recepción: {str(e)}")
    
    # GET request
    context = {
        'warehouses': WarehouseModel.objects.all(),
        'suppliers': SupplierModel.objects.all(),
        'product_types': ProductTypeModel.objects.all()
    }
    
    return render(request, 'nave/record_movement_in.html', context)

def record_movement_out(request):
    return render(request, 'nave/record_movement_out.html')

def pending_distribution_reception(request):
    pending_receptions = MovementInModel.objects.filter(status='PENDING').prefetch_related('items__product_type')
    distributed_receptions = MovementInModel.objects.filter(status='DISTRIBUTED').prefetch_related('items__product_type')
    
    # Agregar información de distribución
    for reception in distributed_receptions:
        for item in reception.items.all():
            item.distributions = MovementInDistributionModel.objects.filter(movement_item=item)

    return render(request, 'nave/pending_distribution_reception.html', {
        'pending_receptions': pending_receptions,
        'distributed_receptions': distributed_receptions
    })

def pending_distribution_items(request, movement_in_id):
    movement = get_object_or_404(MovementInModel, id=movement_in_id)
    grid = get_object_or_404(WarehouseGridModel, warehouse=movement.warehouse)
    
    # Filtrar solo los estantes activos
    shelves = ShelfModel.objects.filter(
        grid=grid, # Solo estantes activos
    )
    
    # Crear un diccionario que mapee cada estante con sus niveles
    shelf_levels = {}
    for shelf in shelves:
        shelf_levels[shelf.id] = list(LevelModel.objects.filter(
            shelf=shelf
        ).order_by('floor_number').values('id', 'floor_number'))
    
    # Obtener todos los items del movimiento con sus detalles
    items = MovementInItemModel.objects.select_related(
        'product_type',
        'movement__supplier'
    ).filter(movement=movement)
    
    # Agregar análisis de ocupación de estantes
    shelf_occupancy = []
    active_shelves = ShelfModel.objects.filter(grid=grid, is_active=True)
    
    for shelf in active_shelves:
        # Calcular totales por estante
        regular_items = (InventoryItemModel.objects
            .filter(level__shelf=shelf)
            .aggregate(
                total_items=models.Sum('quantity'),
                total_weight=models.Sum('weight'),
                total_volume=models.Sum('volume')
            ))
            
        distributed_items = (MovementInDistributionModel.objects
            .filter(level__shelf=shelf)
            .aggregate(
                total_items=models.Sum('quantity'),
                total_weight=models.Sum('weight'),
                total_volume=models.Sum('volume')
            ))
            
        # Calcular totales combinados
        total_items = (regular_items['total_items'] or 0) + (distributed_items['total_items'] or 0)
        total_weight = (regular_items['total_weight'] or 0) + (distributed_items['total_weight'] or 0)
        total_volume = (regular_items['total_volume'] or 0) + (distributed_items['total_volume'] or 0)
        
        # Calcular porcentaje de ocupación (basado en el peso)
        max_weight_capacity = shelf.max_weight if shelf.max_weight > 0 else 1
        occupancy_percentage = (total_weight / max_weight_capacity * 100) if max_weight_capacity else 0
        
        # Determinar el estado de ocupación
        if occupancy_percentage == 0:
            status = 'empty'
        elif occupancy_percentage < 50:
            status = 'low'
        elif occupancy_percentage < 80:
            status = 'medium'
        else:
            status = 'high'

        shelf_occupancy.append({
            'shelf': shelf,
            'total_items': total_items,
            'total_weight': total_weight,
            'total_volume': total_volume,
            'occupancy_percentage': round(occupancy_percentage, 2),
            'status': status,
            'levels_count': shelf.levels.count()
        })
    
    # Ordenar por disponibilidad (menos ocupados primero)
    shelf_occupancy.sort(key=lambda x: x['occupancy_percentage'])

    if request.method == 'POST':
        try:
            item_id = request.POST.get('item_id')
            level_id = request.POST.get('level_id')
            quantity = int(request.POST.get('quantity'))
            
            item = MovementInItemModel.objects.get(id=item_id)
            level = LevelModel.objects.get(id=level_id)
            
            # Validar que la cantidad a distribuir no exceda la cantidad pendiente
            distributed = MovementInDistributionModel.objects.filter(
                movement_item=item
            ).aggregate(total=models.Sum('quantity'))['total'] or 0
            
            if quantity > (item.quantity - distributed):
                raise ValueError("La cantidad a distribuir excede la cantidad pendiente")
            
            # Crear la distribución
            MovementInDistributionModel.objects.create(
                movement_item=item,
                level=level,
                quantity=quantity,
                weight=item.weight,
                volume=item.volume
            )
            
            messages.success(request, f"Se han distribuido {quantity} unidades del producto {item.product_type.name}")
            
            # Verificar si todos los ítems han sido distribuidos
            all_distributed = all(
                MovementInDistributionModel.objects.filter(movement_item=i).aggregate(total=models.Sum('quantity'))['total'] == i.quantity
                for i in items
            )
            
            if all_distributed:
                movement.status = 'DISTRIBUTED'
                movement.distributed_timestamp = timezone.now()
                movement.save()
            
            return redirect('pending_distribution_items', movement_in_id=movement_in_id)
            
        except Exception as e:
            messages.error(request, f"Error al distribuir el item: {str(e)}")
    
    # Para cada item, calcular cantidad distribuida y pendiente
    items_info = []
    for item in items:
        distributed = MovementInDistributionModel.objects.filter(
            movement_item=item
        ).aggregate(total=models.Sum('quantity'))['total'] or 0
        
        # Obtener las distribuciones existentes con información detallada
        distributions = MovementInDistributionModel.objects.filter(
            movement_item=item
        ).select_related(
            'level__shelf',
            'movement_item__product_type'
        ).order_by('-timestamp')  # Ordenar por fecha, más reciente primero
        
        items_info.append({
            'item': item,
            'product_name': item.product_type.name,
            'product_code': item.product_type.codigo,
            'total_quantity': item.quantity,
            'distributed': distributed,
            'pending': item.quantity - distributed,
            'weight': item.weight,
            'volume': item.volume,
            'distributions': [{
                'quantity': dist.quantity,
                'shelf_id': dist.level.shelf.identifier,
                'level_number': dist.level.floor_number,
                'timestamp': dist.timestamp,
                'weight': dist.weight,
                'volume': dist.volume
            } for dist in distributions]
        })

    context = {
        'movement': movement,
        'items_info': items_info,
        'shelves': shelves,
        'shelf_levels': json.dumps(shelf_levels),
        'grid': grid,
        'rows': range(grid.rows),
        'columns': range(grid.columns),
        'shelf_occupancy': shelf_occupancy,
    }
    
    return render(request, 'nave/pending_distribution_items.html', context)

def register_item_movement(request):
    return render(request, 'nave/register_item_movement.html')

def get_shelves(request, warehouse_id):
    shelves = ShelfModel.objects.filter(
        grid__warehouse_id=warehouse_id,
        is_active=True
    )
    data = [{'id': shelf.id, 'name': shelf.identifier} for shelf in shelves]
    return JsonResponse(data, safe=False)

def retirar_producto(request, level_id):
    level = get_object_or_404(LevelModel, id=level_id)
    grid = get_object_or_404(WarehouseGridModel, warehouse=level.shelf.grid.warehouse)
    inventory_items = InventoryItemModel.objects.filter(level=level)
    warehouse_levels = LevelModel.objects.filter(
        shelf__grid__warehouse=level.shelf.grid.warehouse
    ).exclude(id=level_id)
    distributed_items = MovementInDistributionModel.objects.filter(level=level)

    # Obtener información de las distribuciones
    distribution_info = []
    for item in distributed_items:
        distribution_info.append({
            'quantity': item.quantity,
            'shelf': item.level.shelf.identifier,
            'floor': item.level.floor_number,
            'timestamp': item.timestamp,
            'details': f"Distribución inicial de recepción - {item.movement_item.product_type.name}",
            'origin': 'RECEPTION',
            'product_code': item.movement_item.product_type.codigo,
            'product_name': item.movement_item.product_type.name
        })

    # Obtener movimientos internos que se originaron en este nivel
    outgoing_movements = InternalMovementModel.objects.filter(
        source_level=level
    ).select_related(
        'item__product_type',
        'destination_level__shelf'
    ).order_by('-timestamp')

    # Agregar los movimientos salientes al historial
    for movement in outgoing_movements:
        distribution_info.append({
            'quantity': movement.quantity,
            'shelf': movement.destination_level.shelf.identifier,
            'floor': movement.destination_level.floor_number,
            'timestamp': movement.timestamp,
            'details': f"Transferencia hacia {movement.destination_level.shelf.identifier} Nivel {movement.destination_level.floor_number}",
            'origin': 'OUTGOING_TRANSFER',
            'product_code': movement.item.product_type.codigo,
            'product_name': movement.item.product_type.name,
            'destination_shelf': movement.destination_level.shelf.identifier,
            'destination_level': movement.destination_level.floor_number
        })

    # Obtener todos los productos en la estantería actual
    shelf_inventory = []
    shelf_levels = LevelModel.objects.filter(shelf=level.shelf)
    
    for shelf_level in shelf_levels:
        # Obtener items regulares del nivel
        regular_items = InventoryItemModel.objects.filter(level=shelf_level)
        # Obtener items distribuidos del nivel
        distributed_items_level = MovementInDistributionModel.objects.filter(level=shelf_level)
        
        shelf_inventory.append({
            'level_number': shelf_level.floor_number,
            'regular_items': [{
                'name': item.product_name,
                'code': item.product_type.codigo,
                'quantity': item.quantity,
                'weight': item.weight,
                'volume': item.volume
            } for item in regular_items],
            'distributed_items': [{
                'name': item.movement_item.product_type.name,
                'code': item.movement_item.product_type.codigo,
                'quantity': item.quantity,
                'weight': item.weight,
                'volume': item.volume
            } for item in distributed_items_level]
        })

    # Ordenar todo el historial por fecha
    distribution_info.sort(key=lambda x: x['timestamp'], reverse=True)

    # Obtener todos los almacenes disponibles
    warehouses = WarehouseModel.objects.exclude(id=level.shelf.grid.warehouse.id)

    # Agregar cálculo de ocupación de estantes
    shelf_occupancy = []
    active_shelves = ShelfModel.objects.filter(grid=grid, is_active=True)
    
    for shelf in active_shelves:
        # Calcular totales por estante
        regular_items = (InventoryItemModel.objects
            .filter(level__shelf=shelf)
            .aggregate(
                total_items=models.Sum('quantity'),
                total_weight=models.Sum('weight'),
                total_volume=models.Sum('volume')
            ))
            
        distributed_items = (MovementInDistributionModel.objects
            .filter(level__shelf=shelf)
            .aggregate(
                total_items=models.Sum('quantity'),
                total_weight=models.Sum('weight'),
                total_volume=models.Sum('volume')
            ))
            
        # Calcular totales combinados
        total_items = (regular_items['total_items'] or 0) + (distributed_items['total_items'] or 0)
        total_weight = (regular_items['total_weight'] or 0) + (distributed_items['total_weight'] or 0)
        total_volume = (regular_items['total_volume'] or 0) + (distributed_items['total_volume'] or 0)
        
        # Calcular porcentajes de ocupación
        weight_capacity = shelf.max_weight if shelf.max_weight > 0 else 1
        volume_capacity = shelf.max_volume if shelf.max_volume > 0 else 1
        
        weight_occupancy = (total_weight / weight_capacity * 100) if weight_capacity else 0
        volume_occupancy = (total_volume / volume_capacity * 100) if volume_capacity else 0
        
        # Determinar el estado de ocupación
        if weight_occupancy == 0 and volume_occupancy == 0:
            status = 'empty'
        elif weight_occupancy < 50 and volume_occupancy < 50:
            status = 'low'
        elif weight_occupancy < 80 and volume_occupancy < 80:
            status = 'medium'
        else:
            status = 'high'

        shelf_occupancy.append({
            'shelf': shelf,
            'total_items': total_items,
            'total_weight': total_weight,
            'total_volume': total_volume,
            'weight_occupancy': weight_occupancy,
            'volume_occupancy': volume_occupancy,
            'status': status,
            'available_weight': weight_capacity - total_weight,
            'available_volume': volume_capacity - total_volume,
            'levels_info': [{
                'level': level,
                'items_count': InventoryItemModel.objects.filter(level=level).count() + 
                             MovementInDistributionModel.objects.filter(level=level).count()
            } for level in shelf.levels.all()]
        })
    
    # Ordenar por disponibilidad (menos ocupados primero)
    shelf_occupancy.sort(key=lambda x: (x['weight_occupancy'] + x['volume_occupancy'])/2)
    
    if request.method == 'POST':
        try:
            item_id = request.POST.get('item_id')
            quantity = int(request.POST.get('quantity'))
            action = request.POST.get('action')
            destination = request.POST.get('destination')

            # Verificar si el item es un MovementInDistributionModel
            is_distributed_item = MovementInDistributionModel.objects.filter(id=item_id).exists()
            
            if is_distributed_item:
                item = MovementInDistributionModel.objects.get(id=item_id)
            else:
                item = InventoryItemModel.objects.get(id=item_id)

            if action == 'transfer_within':
                try:
                    destination_level = LevelModel.objects.get(id=destination)
                    
                    if is_distributed_item:
                        # Crear o actualizar el InventoryItem en el destino
                        destination_item, created = InventoryItemModel.objects.get_or_create(
                            level=destination_level,
                            product_type=item.movement_item.product_type,
                            supplier=item.movement_item.movement.supplier,
                            product_name=item.movement_item.product_type.name,
                            defaults={
                                'quantity': quantity,
                                'weight': item.weight,
                                'volume': item.volume
                            }
                        )
                        
                        if not created:  # Si ya existía, actualizar la cantidad
                            destination_item.quantity += quantity
                            destination_item.save()
                            
                        # Actualizar o eliminar el item original
                        item.quantity -= quantity
                        if item.quantity <= 0:
                            item.delete()
                        else:
                            item.save()
                        
                        # Registrar el movimiento interno para items distribuidos
                        InternalMovementModel.objects.create(
                            item=destination_item,
                            source_level=level,
                            destination_level=destination_level,
                            quantity=quantity,
                            performed_by=request.user if request.user.is_authenticated else None,
                            source_shelf_identifier=level.shelf.identifier,
                            source_level_number=level.floor_number
                        )
                    else:
                        # Para items regulares
                        destination_item, created = InventoryItemModel.objects.get_or_create(
                            level=destination_level,
                            product_type=item.product_type,
                            supplier=item.supplier,
                            product_name=item.product_name,
                            defaults={
                                'quantity': quantity,
                                'weight': item.weight,
                                'volume': item.volume
                            }
                        )
                        
                        if not created:  # Si ya existía, actualizar la cantidad
                            destination_item.quantity += quantity
                            destination_item.save()

                        # Registrar el movimiento interno
                        InternalMovementModel.objects.create(
                            item=item,
                            source_level=level,
                            destination_level=destination_level,
                            quantity=quantity,
                            performed_by=request.user if request.user.is_authenticated else None,
                            source_shelf_identifier=level.shelf.identifier,
                            source_level_number=level.floor_number
                        )
                        
                        # Actualizar o eliminar el item original
                        item.quantity -= quantity
                        if item.quantity <= 0:
                            item.delete()
                        else:
                            item.save()

                    messages.success(
                        request,
                        f"Transferencia exitosa: {quantity} unidades hacia Nivel {destination_level.floor_number} (Estante {destination_level.shelf.identifier})"
                    )
                    
                    # Redirigir después de una transferencia exitosa
                    return redirect('retirar_producto', level_id=level_id)

                except LevelModel.DoesNotExist:
                    raise ValueError("El nivel de destino no existe")

            elif action == 'transfer_warehouse':
                try:
                    destination_warehouse = WarehouseModel.objects.get(id=destination)
                    
                    # Encontrar un nivel disponible en el almacén de destino
                    destination_level = LevelModel.objects.filter(
                        shelf__grid__warehouse=destination_warehouse,
                        shelf__is_active=True
                    ).first()
                    
                    if not destination_level:
                        messages.error(
                            request,
                            f"Error: No hay niveles disponibles en el almacén {destination_warehouse.name}. "
                            "Asegúrese de que exista al menos un estante activo."
                        )
                        return redirect('retirar_producto', level_id=level_id)
                    
                    if is_distributed_item:
                        try:
                            # Primero crear el InventoryItem en el destino
                            destination_item = InventoryItemModel.objects.create(
                                level=destination_level,
                                product_type=item.movement_item.product_type,
                                supplier=item.movement_item.movement.supplier,
                                product_name=item.movement_item.product_type.name,
                                quantity=quantity,
                                weight=item.weight,
                                volume=item.volume
                            )
                            
                            # Luego crear el movimiento
                            MovementModel.objects.create(
                                item=destination_item,
                                movement_type='TRANSFER',
                                quantity=quantity,
                                source_warehouse=level.shelf.grid.warehouse,
                                destination_warehouse=destination_warehouse,
                                performed_by=request.user if request.user.is_authenticated else None
                            )
                            
                            # Actualizar o eliminar el item distribuido original
                            item.quantity -= quantity
                            if item.quantity <= 0:
                                item.delete()
                            else:
                                item.save()
                                
                            messages.success(
                                request,
                                f"Transferencia exitosa:\n"
                                f"- Producto: {item.movement_item.product_type.name}\n"
                                f"- Cantidad: {quantity} unidades\n"
                                f"- Desde: Almacén {level.shelf.grid.warehouse.name}, Estante {level.shelf.identifier}, Nivel {level.floor_number}\n"
                                f"- Hacia: Almacén {destination_warehouse.name}, Estante {destination_level.shelf.identifier}, Nivel {destination_level.floor_number}\n"
                                f"- Estado: Item distribuido convertido a inventario regular"
                            )
                            
                        except Exception as e:
                            messages.error(
                                request,
                                f"Error al transferir item distribuido:\n"
                                f"- Producto: {item.movement_item.product_type.name}\n"
                                f"- Error: {str(e)}"
                            )
                            raise e
                            
                    else:
                        try:
                            # Para items regulares, crear nuevo item en destino
                            destination_item = InventoryItemModel.objects.create(
                                level=destination_level,
                                product_type=item.product_type,
                                supplier=item.supplier,
                                product_name=item.product_name,
                                quantity=quantity,
                                weight=item.weight,
                                volume=item.volume
                            )
                            
                            # Crear el movimiento
                            MovementModel.objects.create(
                                item=destination_item,
                                movement_type='TRANSFER',
                                quantity=quantity,
                                source_warehouse=level.shelf.grid.warehouse,
                                destination_warehouse=destination_warehouse,
                                performed_by=request.user if request.user.is_authenticated else None
                            )
                            
                            # Actualizar o eliminar el item original
                            item.quantity -= quantity
                            if item.quantity <= 0:
                                item.delete()
                            else:
                                item.save()
                            
                            messages.success(
                                request,
                                f"Transferencia exitosa:\n"
                                f"- Producto: {item.product_name}\n"
                                f"- Cantidad: {quantity} unidades\n"
                                f"- Desde: Almacén {level.shelf.grid.warehouse.name}, Estante {level.shelf.identifier}, Nivel {level.floor_number}\n"
                                f"- Hacia: Almacén {destination_warehouse.name}, Estante {destination_level.shelf.identifier}, Nivel {destination_level.floor_number}"
                            )
                            
                        except Exception as e:
                            messages.error(
                                request,
                                f"Error al transferir item regular:\n"
                                f"- Producto: {item.product_name}\n"
                                f"- Error: {str(e)}"
                            )
                            raise e

                    return redirect('retirar_producto', level_id=level_id)

                except WarehouseModel.DoesNotExist:
                    messages.error(request, f"Error: El almacén de destino no existe o no está disponible.")
                except ValueError as e:
                    messages.error(request, f"Error de validación: {str(e)}")
                except Exception as e:
                    messages.error(
                        request,
                        f"Error inesperado durante la transferencia:\n"
                        f"- Tipo de error: {type(e).__name__}\n"
                        f"- Detalles: {str(e)}"
                    )

            context = {
                'level': level,
                'inventory_items': inventory_items,
                'distributed_items': distributed_items,
                'warehouse_levels': warehouse_levels,
                'warehouses': warehouses,
                'grid': grid,
                'rows': range(grid.rows),
                'columns': range(grid.columns),
                'shelves': ShelfModel.objects.filter(grid=grid),
                'distribution_info': distribution_info,
                'shelf_inventory': shelf_inventory,
                'shelf_occupancy': shelf_occupancy,
            }
            return render(request, 'nave/retirar_producto.html', context)

        except ValueError as e:
            messages.error(request, f"Error de validación: {str(e)}")
            print(f"Error de validación: {str(e)}")  # Debug
        except Exception as e:
            messages.error(request, f"Error inesperado: {str(e)}")
            print(f"Error inesperado: {str(e)}")  # Debug
            logger.error(f"Error en retirar_producto: {str(e)}", exc_info=True)

    # Definición de context para GET request y casos de error
    context = {
        'level': level,
        'inventory_items': inventory_items,
        'distributed_items': distributed_items,
        'warehouse_levels': warehouse_levels,
        'warehouses': warehouses,
        'grid': grid,
        'rows': range(grid.rows),
        'columns': range(grid.columns),
        'shelves': ShelfModel.objects.filter(grid=grid),
        'distribution_info': distribution_info,
        'shelf_inventory': shelf_inventory,
        'shelf_occupancy': shelf_occupancy,
    }
    return render(request, 'nave/retirar_producto.html', context)
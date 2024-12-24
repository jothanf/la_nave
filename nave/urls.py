from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('register_warehouse/', views.registerWarehouse, name='register_warehouse'),
    path('warehouse/<int:warehouse_id>/', views.warehouse_detail, name='warehouse_detail'),
    path('warehouse/<int:warehouse_id>/configure/', views.configure_warehouse, name='configure_warehouse'),
    path('shelf/<int:shelf_id>/info/', views.shelf_info, name='shelf_info'),
    path('level/<int:level_id>/add_item/', views.add_inventory_item, name='add_inventory_item'),
    path('add_supplier/', views.add_supplier, name='add_supplier'),
    path('add_product_type/', views.add_product_type, name='add_product_type'),
    path('record_movement_in/', views.record_movement_in, name='record_movement_in'),
    path('record_movement_out/', views.record_movement_out, name='record_movement_out'),
    path('pending_distribution_reception/', views.pending_distribution_reception, name='pending_distribution_reception'),
    path('pending_distribution_items/<int:movement_in_id>/', views.pending_distribution_items, name='pending_distribution_items'),
    path('register_item_movement/', views.register_item_movement, name='register_item_movement'),
    path('login/', auth_views.LoginView.as_view(template_name='nave/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('level/<int:level_id>/retirar/', views.retirar_producto, name='retirar_producto'),
] 
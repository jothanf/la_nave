from django import forms
from .models import InventoryItemModel, MovementModel

class InventoryItemForm(forms.ModelForm):
    class Meta:
        model = InventoryItemModel
        fields = ['product_type', 'supplier', 'product_name', 'quantity', 'weight', 'volume']
        widgets = {
            'product_type': forms.Select(attrs={'class': 'form-control'}),
            'supplier': forms.Select(attrs={'class': 'form-control'}),
            'product_name': forms.TextInput(attrs={'class': 'form-control'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control'}),
            'weight': forms.NumberInput(attrs={'class': 'form-control'}),
            'volume': forms.NumberInput(attrs={'class': 'form-control'}),
        }

class MovementForm(forms.ModelForm):
    class Meta:
        model = MovementModel
        fields = ['movement_type', 'quantity']
        widgets = {
            'movement_type': forms.Select(attrs={'class': 'form-control'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control'}),
        } 
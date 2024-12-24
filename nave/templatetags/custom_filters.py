from django import template

register = template.Library()

@register.filter
def get_item(dictionary, key):
    if isinstance(dictionary, dict):
        return dictionary.get(key)
    return None 

@register.filter
def range_filter(number):
    return range(number) 

@register.filter
def contains(value_list, item):
    if isinstance(value_list, set):
        return item in value_list
    return False

@register.filter
def get_shelf(shelves, position_key):
    return shelves.filter(position_key=position_key).first()
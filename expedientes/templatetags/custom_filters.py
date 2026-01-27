from django import template

register = template.Library()

@register.filter
def get_item(dictionary, key):
    """
    Uso en template: {{ diccionario|get_item:clave }}
    Permite obtener valores de un diccionario usando una variable como clave.
    """
    if dictionary:
        return dictionary.get(key, '')
    return ''
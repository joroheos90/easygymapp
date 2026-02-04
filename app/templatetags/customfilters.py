import re
from django import template
from django.forms import BoundField
from django.utils.html import format_html

register = template.Library()

@register.filter
def first_name(full_name):
    if not full_name:
        return ""

    return full_name.strip().split()[0]

@register.filter
def initials(value: str, max_letters: int = 2) -> str:
    if not value:
        return ""
    letters = re.findall(r"\b(\w)", value.strip(), flags=re.UNICODE)
    return "".join(letters[:int(max_letters)]).upper()


@register.filter
def add_class(field, css_class):
    if isinstance(field, BoundField):
        return format_html(
            '<input type="{}" name="{}" class="{}" value="{}">',
            field.field.widget.input_type,
            field.name,
            css_class,
            field.value() or ''
        )
    return field

@register.filter
def get_item(d, key):
    if not d:
        return ""
    return d.get(key, "")


@register.filter
def percent_of(value, max_value):
    try:
        min_base = 40 
        percent = ((float(value) - min_base) / (float(max_value) - min_base)) * 100
        return f"{percent:.2f}"
    except (ValueError, ZeroDivisionError):
        return "0"


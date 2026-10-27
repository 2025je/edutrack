import os

from django import template
from django.conf import settings
from django.contrib.staticfiles import finders
from django.templatetags.static import static

register = template.Library()
_versions = {}


@register.simple_tag
def asset(path):
    """URL estática con `?v=<fecha de modificación>` para poder cachearla mucho tiempo."""
    version = _versions.get(path)
    if version is None or settings.DEBUG:
        found = finders.find(path)
        version = str(int(os.path.getmtime(found))) if isinstance(found, str) else "0"
        _versions[path] = version
    return f"{static(path)}?v={version}"

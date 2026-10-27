"""WSGI config for the factory planner web application."""

import os

from django.core.wsgi import get_wsgi_application


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "factory_planner_web.settings")

application = get_wsgi_application()

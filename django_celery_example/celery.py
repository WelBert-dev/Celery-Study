"""
https://docs.celeryq.dev/en/stable/django/first-steps-with-django.html
"""
import os

from celery import Celery

from django.conf import settings

from polls.scrapers import ScraperUtil

# this code copied from manage.py
# set the default Django settings module for the 'celery' app.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'django_celery_example.settings')

# you can change the name here
app = Celery("django_celery_example")

# read config from Django settings, the CELERY namespace would make celery
# config keys has `CELERY` prefix
app.config_from_object('django.conf:settings', namespace='CELERY')

# discover and load tasks.py from from all registered Django apps
app.autodiscover_tasks(lambda: settings.INSTALLED_APPS)


@app.task
def divide(x, y):
    import time
    time.sleep(5)
    return x / y


@app.task
def run_scraper_with_all_params_task(secao : str, 
                                data : str, 
                                detailDOUJournalFlag : bool, 
                                balancerFlag : bool):
    
    
    return ScraperUtil.run_scraper_with_all_params(secaoURLQueryString_param=secao, 
                                            dataURLQueryString_param=data,
                                            detailDOUJournalFlag=detailDOUJournalFlag,
                                            balancerFlag=balancerFlag)

    

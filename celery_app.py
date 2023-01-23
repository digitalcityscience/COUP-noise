from celery import Celery

app = Celery('celery-app')
app.config_from_object('config')

if __name__ == '__main__':
    app.start()

from django.urls import path
from sunndari_apps.notifications.controllers.notification import NotificationController

urlpatterns = [
    path('get/', NotificationController.get_notification, name='get_notification'),
    path('get_all/', NotificationController.get_all_notifications, name='get_all_notifications'),
    path('mark_read/', NotificationController.mark_read, name='mark_notification_read'),
    path('mark_all_read/', NotificationController.mark_all_read, name='mark_all_notifications_read'),
]

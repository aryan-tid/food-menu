from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    path('login/', views.google_login_view, name='google_login'),
    path('firebase-login/', views.firebase_login_view, name='firebase_login'),
    path('staff-login/', views.staff_login_view, name='staff_login'),
    path('logout/', views.logout_view, name='logout'),
    path('profile/', views.profile_view, name='profile'),
]

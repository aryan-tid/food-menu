from django.urls import path
from . import views

app_name = 'menu'

urlpatterns = [
    path('', views.home_view, name='home'),
    path('menu/', views.menu_list_view, name='menu_list'),
    path('set-table/', views.set_table_view, name='set_table'),
    path('item/<int:item_id>/', views.item_detail_view, name='item_detail'),
    path('item/<int:item_id>/review/', views.submit_review_view, name='submit_review'),
    path('my-reviews/', views.my_reviews_view, name='my_reviews'),
    path('review/<int:review_id>/edit/', views.edit_review_view, name='edit_review'),
    path('review/<int:review_id>/delete/', views.delete_review_view, name='delete_review'),
    path('api/item/<int:item_id>/reviews/', views.api_item_reviews, name='api_item_reviews'),
]

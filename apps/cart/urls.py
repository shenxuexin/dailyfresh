from django.conf.urls import url
from apps.cart import views

urlpatterns = [
    url(r'^add$', views.CartAddView.as_view(), name='cart_add'),
    url(r'^$', views.CartInfoView.as_view(), name='cart_info'),
    url(r'^update$', views.CartUpdateView.as_view(), name='cart_update'),
    url(r'^delete$', views.CartDeleteView.as_view(), name='cart_delete'),
]

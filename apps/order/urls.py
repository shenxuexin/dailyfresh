from django.conf.urls import url
from apps.order import views

urlpatterns = [
    url(r'^$', views.OrderInfoView.as_view(), name='show'),
    url(r'^commit$', views.OrderCommitView.as_view(), name='commit'),
    url(r'^pay$', views.OrderPayView.as_view(), name='pay'),
    url(r'^check$', views.PayCheckView.as_view(), name='check'),
    url(r'^comment/(?P<order_id>\d+)$', views.OrderCommentView.as_view(), name='comment'),
]

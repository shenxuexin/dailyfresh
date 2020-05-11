from django.conf.urls import url
from apps.user import views


urlpatterns = [
    url(r'^register$', views.RegisterView.as_view(), name='register'),
    url(r'^active/(?P<token>.*)', views.ActiveView.as_view(), name='active'),
    url(r'^login$', views.LoginView.as_view(), name='login'),
    url(r'^logout$', views.LogoutView.as_view(), name='logout'),
    url(r'^$', views.UserInfoView.as_view(), name='user_center_info'),
    url(r'^user_center_order/(?P<page>\d+)$', views.UserOrderView.as_view(), name='user_center_order'),
    url(r'^user_center_site$', views.UserSiteView.as_view(), name='user_center_site'),
]

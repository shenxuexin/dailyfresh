from django.template import Library
from apps.goods.models import GoodsType
from django_redis import get_redis_connection

register = Library()


@register.filter
def get_obj(value, name):
    '''查询类'''
    if value:
        return value

    if name == 'types':
        types = GoodsType.objects.all()
        return types


@register.filter
def get_cart_count(value, user):
    '''获取购物车数量'''
    if value:
        return value

    cart_count = 0
    if user.is_authenticated():
        conn = get_redis_connection('default')
        cart_key = 'cart_%d' % user.id
        cart_count = conn.hlen(cart_key)

    return cart_count
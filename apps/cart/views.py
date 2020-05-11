from django.shortcuts import render
from django.views.generic import View
from django.http import JsonResponse
from apps.goods.models import GoodsSKU
from django_redis import get_redis_connection
from util.mixin import LoginRequiredMixin


# Create your views here.
# /cart/add  sku_id count
class CartAddView(View):
    '''购物车添加视图类'''
    def post(self, request):
        # 校验用户登录
        user = request.user
        if not user.is_authenticated():
            return JsonResponse({'res': 0, 'errmsg': '用户未登录'})

        # 获取数据
        sku_id = request.POST.get('sku_id')
        count = request.POST.get('count')

        # 校验数据
        # 校验数据完整性
        if not all([sku_id, count]):
            return JsonResponse({'res': 1, 'errmsg': '数据不完整'})

        # 校验商品数目是否合法
        try:
            count = int(count)
        except Exception as e:
            return JsonResponse({'res': 2, 'errmsg': '商品数目有误'})

        # 校验商品是否存在
        try:
            sku = GoodsSKU.objects.get(id=sku_id)
        except GoodsSKU.DoesNotExist:
            return JsonResponse({'res': 3, 'errmsg': '商品不存在'})

        # 业务处理: 添加购物车
        # 根据redis数据库中是否存在当前商品选择是否累计
        conn = get_redis_connection('default')
        cart_key = 'cart_%d' % user.id
        cart_count = conn.hget(cart_key, sku_id)
        if cart_count:
            count += int(cart_count)

        # 校验是否超过库存
        if count > sku.stock:
            return JsonResponse({'res': 4, 'errmsg': '商品库存不足'})

        conn.hset(cart_key, sku_id, count)

        # 查询购物车数目
        total_count = conn.hlen(cart_key)

        # 返回响应
        return JsonResponse({'res': 5, 'total_count':total_count, 'msg': '添加购物车成功'})


# /cart
class CartInfoView(LoginRequiredMixin, View):
    '''购物车页面'''
    def get(self, request):
        # 获取用户的商品记录
        conn = get_redis_connection('default')
        cart_key = 'cart_%d' % request.user.id
        cart_dict = conn.hgetall(cart_key)

        # 添加商品到skus, 计算总价和总数量
        skus = list()
        total_count = 0
        total_price = 0
        for sku_id, count in cart_dict.items():
            sku = GoodsSKU.objects.get(id=sku_id)
            amount = sku.price*int(count)
            sku.amount = amount
            sku.count = count

            skus.append(sku)
            total_price += amount
            total_count += int(count)

        # 组织上下文
        context = {
            'total_count': total_count,
            'total_price': total_price,
            'skus': skus
        }

        return render(request, 'cart.html', context)


# /cart/update
class CartUpdateView(View):
    '''更新购物车视图类'''
    def post(self, request):
        # 登录校验
        user = request.user
        if not user.is_authenticated():
            return JsonResponse({'res': 0, 'errmsg': '用户未登录'})

        # 接收数据
        sku_id = request.POST.get('sku_id')
        count = request.POST.get('count')

        # 校验数据
        # 数据完整性
        if not all([sku_id, count]):
            return JsonResponse({'res': 1, 'errmsg': '数据不完整'})

        # 数目合法
        try:
            count = int(count)
        except Exception as e:
            return JsonResponse({'res': 2, 'errmsg': '无效的商品数目'})

        # 商品是否存在
        try:
            sku = GoodsSKU.objects.get(id=sku_id)
        except GoodsSKU.DoesNotExist:
            return JsonResponse({'res': 3, 'errmsg': '商品不存在'})

        # 业务处理: 更新购物车
        conn = get_redis_connection('default')
        cart_key = 'cart_%d' % user.id

        # 验证是否超过库存
        if count > sku.stock:
            return JsonResponse({'res': 4, 'errmsg': '商品库存不足'})

        conn.hset(cart_key, sku_id, count)

        # 查询购物车总数目
        total = 0
        for val in conn.hvals(cart_key):
            total += int(val)

        # 返回响应
        return JsonResponse({'res': 5, 'total': total, 'msg': '购物车更新成功!'})

# /cart/delete  sku_id
class CartDeleteView(View):
    '''删除购物车视图'''
    def post(self, request):
        # 登录校验
        user = request.user
        if not user.is_authenticated():
            return JsonResponse({'res': 0, 'errmsg': '用户未登录'})

        # 接收数据
        sku_id = request.POST.get('sku_id')

        # 校验数据
        # 数据完整性
        if not sku_id:
            return JsonResponse({'res': 1, 'errmsg': '无效的商品id'})

        # 商品是否存在
        try:
            sku = GoodsSKU.objects.get(id=sku_id)
        except GoodsSKU.DoesNotExist:
            return JsonResponse({'res': 2, 'errmsg': '商品不存在'})

        # 业务处理: 删除购物车商品
        conn = get_redis_connection('default')
        cart_key = 'cart_%d' % user.id

        conn.hdel(cart_key, sku_id)

        # 查询购物车总数目
        total = 0
        for val in conn.hvals(cart_key):
            total += int(val)

        # 返回响应
        return JsonResponse({'res': 3, 'total': total, 'msg': '删除购物车商品成功!'})
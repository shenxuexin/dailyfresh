from django.shortcuts import render, redirect
from django.core.urlresolvers import reverse
from django.views.generic import View
from apps.goods.models import GoodsType, IndexTypeGoodsBanner, IndexGoodsBanner, IndexPromotionBanner, GoodsSKU
from apps.order.models import OrderGoods
from django_redis import get_redis_connection
from django.core.cache import cache
from django.core.paginator import Paginator

# Create your views here.
class IndexView(View):
    '''首页'''
    def get(self, request):
        # 获取缓存信息
        context = cache.get('index_page_data')

        if context is None:
            # 获取首页商品分类
            types = GoodsType.objects.all()

            # 获取首页商品轮播图
            goods_banners = IndexGoodsBanner.objects.all().order_by('index')

            # 获取首页促销图片
            promotion_banners = IndexPromotionBanner.objects.all().order_by('index')

            # 获取首页分类展示图片
            for type in types:
                title_banners = IndexTypeGoodsBanner.objects.filter(type=type)
                display_banners = IndexTypeGoodsBanner.objects.filter(type=type)[:4]

                type.title_banners = title_banners
                type.display_banners = display_banners

            context = {
                'types': types,
                'goods_banners': goods_banners,
                'promotion_banners': promotion_banners,
            }

            # 设置缓存信息
            cache.set('index_page_data', context, 3600)
            print('======>缓存设置')

        # 获得购物车数量
        cart_count = 0
        # 从缓存中存储并获取购物车数量: 存储格式为  cart_用户id: {'sku_id1': num1, 'sku_id2':num2...}
        user = request.user
        if user.is_authenticated():
            # 连接redis
            conn = get_redis_connection('default')

            # 获取数据
            cart_key = 'cart_%d' % user.id
            cart_count = conn.hlen(cart_key)

        # 构建上下文
        context.update(cart_count=cart_count)

        return render(request, 'index.html', context)


class DetailView(View):
    '''详情页视图'''
    def get(self, request, sku_id):
        # 获取sku
        try:
            sku = GoodsSKU.objects.get(id=sku_id)
        except GoodsSKU.DoesNotExist:
            return redirect(reverse('goods:index'))

        # 获取商品分类
        types = GoodsType.objects.all()

        # 获取商品评论
        sku_order = OrderGoods.objects.filter(sku=sku).exclude(comment='')

        # 获取新品
        new_goods = GoodsSKU.objects.filter(type=sku.type).exclude(id=sku_id).order_by('create_time')[:2]

        # 获取其他规格商品
        same_spu_sku = GoodsSKU.objects.filter(goods=sku.goods).exclude(id=sku_id)

        # 获取购物车数量
        cart_count = 0
        # 从缓存中存储并获取购物车数量: 存储格式为  cart_用户id: {'sku_id1': num1, 'sku_id2':num2...}
        user = request.user
        if user.is_authenticated():
            # 连接redis
            conn = get_redis_connection('default')

            # 获取数据
            cart_key = 'cart_%d' % user.id
            cart_count = conn.hlen(cart_key)

            # 添加用户最近浏览记录:存储格式为 history_用户id:[1,2,3...]
            # 连接redis数据库
            conn = get_redis_connection('default')

            # 删除原先相同的商品id
            history_key = 'history_%d' % user.id
            conn.lrem(history_key, 0, sku_id)

            # 添加商品id
            conn.lpush(history_key, sku_id)

            # 截取五个浏览记录
            conn.ltrim(history_key, 0, 4)


        # 构建上下文
        context = {
            'sku': sku,
            'types': types,
            'sku_order': sku_order,
            'new_goods': new_goods,
            'same_spu_sku': same_spu_sku,
            'cart_count': cart_count
        }

        return render(request, 'detail.html', context)


class ListView(View):
    '''列表视图类'''
    def get(self, request, type_id, page):
        # 获取当前分类
        try:
            type = GoodsType.objects.get(id=type_id)
        except GoodsType.DoesNotExist:
            return redirect(reverse('goods:index'))

        # 获取所有商品分类
        types = GoodsType.objects.all()

        # 获取分类商品: 排序
        sort = request.GET.get('sort')
        if sort == 'price':
            skus = GoodsSKU.objects.filter(type=type).order_by('price')
        elif sort == 'hot':
            skus = GoodsSKU.objects.filter(type=type).order_by('-sales')
        else:
            sort = 'default'
            skus = GoodsSKU.objects.filter(type=type).order_by('id')

        # 获取分页
        # 分页
        paginator = Paginator(skus, 5)

        # 获取当前页
        try:
            page = int(page)
        except Exception as e:
            page = 1
        if page > paginator.num_pages or page < 1:
            page = 1

        sku_page = paginator.page(page)

        # 组织页码
        page_num = paginator.num_pages
        if page_num < 5:
            pages = range(1, page_num+1)
        elif page <= 3:
            pages = range(1, 6)
        elif page_num - page <= 2:
            pages = range(page_num-4, page_num+1)
        else:
            pages = range(page-2, page+3)

        # 获取新品推荐
        new_skus = GoodsSKU.objects.filter(type=type).order_by('create_time')[:2]

        # 获取购物车数量
        cart_count = 0
        user = request.user
        if user.is_authenticated():
            # 连接redis
            conn = get_redis_connection('default')

            # 获取数据
            cart_key = 'cart_%d' % user.id
            cart_count = conn.hlen(cart_key)

        # 组织上下文
        context = {
            'type': type,
            'types': types,
            'sort': sort,
            'sku_page': sku_page,
            'pages': pages,
            'new_skus': new_skus,
            'cart_count': cart_count
        }

        return render(request, 'list.html', context)
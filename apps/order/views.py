from django.shortcuts import render, redirect
from django.http import JsonResponse, HttpResponse
from django.views.generic import View
from apps.user.models import Address
from apps.goods.models import GoodsSKU
from django.core.urlresolvers import reverse
from util.mixin import LoginRequiredMixin
from django_redis import get_redis_connection
from apps.order.models import OrderGoods, OrderInfo
from datetime import datetime
from django.db import transaction
from django.conf import settings
import os

# python-alipay-sdk
from alipay import AliPay


def create_context(user, sku_ids):
    # 获取地址
    addrs = Address.objects.filter(user=user)

    # 获取商品
    conn = get_redis_connection('default')
    cart_key = 'cart_%d' % user.id
    total_count = 0
    total_price = 0
    skus = list()

    for sku_id in sku_ids:
        try:
            sku = GoodsSKU.objects.get(id=sku_id)
        except GoodsSKU.DoesNotExist:
            return redirect(reverse('cart:cart_info'))

        count = conn.hget(cart_key, sku_id)
        amount = sku.price * int(count)
        sku.count = count
        sku.amount = amount

        skus.append(sku)
        total_count += int(count)
        total_price += amount

    # 运费
    transit_pay = 10

    # 实付款
    last_pay = total_price + transit_pay

    # 组织sku_ids字符串
    sku_ids = ','.join(sku_ids)

    # 组织上下文
    context = {
        'skus': skus,
        'addrs': addrs,
        'total_count': total_count,
        'total_price': total_price,
        'transit_pay': transit_pay,
        'last_pay': last_pay,
        'sku_ids': sku_ids
    }

    return context

# Create your views here.
class OrderInfoView(LoginRequiredMixin, View):
    '''订单显示视图'''
    def get(self, request):
        user = request.user
        sku_id = request.GET.get('sku_id')

        sku_ids = [sku_id]
        print(sku_id)

        context = create_context(user, sku_ids)
        print('==============>'+str(context))

        return render(request, 'place_order.html', context)


    def post(self, request):
        # 接收数据
        user = request.user
        sku_ids = request.POST.getlist('sku_ids')

        # 校验数据
        if not sku_ids:
            return redirect(reverse('cart:cart_info'))

        # 组织上下文
        context = create_context(user, sku_ids)

        print('post==============>'+str(context))

        return render(request, 'place_order.html', context)




# /order/commit  前端: addr_id, pay_method, sku_ids
class OrderCommitView(View):
    '''订单提交视图'''
    @transaction.atomic
    def post(self, request):
        # 登录验证
        user = request.user
        if not user.is_authenticated():
            return JsonResponse({'res': 0, 'errmsg': '用户未登录'})

        # 接收数据
        addr_id = request.POST.get('addr_id')
        pay_method = request.POST.get('pay_method')
        sku_ids = request.POST.get('sku_ids')

        # 校验数据
        # 数据完整
        if not all([addr_id, pay_method, sku_ids]):
            return JsonResponse({'res': 1, 'errmsg': '参数不完整'})

        # 地址合法性
        try:
            addr = Address.objects.get(id=addr_id)
        except Address.DoesNotExist:
            return JsonResponse({'res': 2, 'errmsg': '地址不合法'})

        # 支付方式合法性
        if pay_method not in OrderInfo.PAY_METHOD_DICT.keys():
            return JsonResponse({'res': 3, 'errmsg': '支付方式不合法'})

        # 设置存档点
        save_id = transaction.savepoint()

        # 业务处理: 创建订单
        try:
            # 添加df_order_info记录
            order_id = datetime.now().strftime('%Y%m%d%H%M%S') + str(user.id)
            total_count = 0
            total_price = 0
            transit_price = 10
            order = OrderInfo.objects.create(order_id=order_id,
                                             user=user,
                                             addr=addr,
                                             pay_method=int(pay_method),
                                             total_count=total_count,
                                             total_price=total_price,
                                             transit_price=transit_price)

            # 添加df_order_goods记录(验证商品,计算总数目和总价格,更新库存和销量)
            sku_ids = sku_ids.split(',')
            conn = get_redis_connection('default')
            cart_key = 'cart_%d' % user.id
            for sku_id in sku_ids:
                for i in range(3):
                    try:
                        # 悲观锁: 查询时锁定,事务结束释放
                        # select * from df_goods_sku where id=sku_id for update;
                        # sku = GoodsSKU.objects.select_for_update().get(id=sku_id)
                        sku = GoodsSKU.objects.get(id=sku_id)
                    except GoodsSKU.DoesNotExist:
                        transaction.savepoint_rollback(save_id)
                        return JsonResponse({'res': 4, 'errmsg': '商品不存在'})

                    count = conn.hget(cart_key, sku_id)
                    amount = sku.price*int(count)

                    # 查询库存
                    if int(count) > sku.stock:
                        transaction.savepoint_rollback(save_id)
                        return JsonResponse({'res': 5, 'errmsg': '商品%s库存不足'%sku.name})

                    # 乐观锁: 查询时不锁定, 更新时检查库存是否修改,循环+设置mysql事务隔离级别为read-committed
                    # 更新库存和销量
                    old_stock = sku.stock
                    new_stock = old_stock - int(count)
                    new_sales = sku.sales + int(count)
                    res = GoodsSKU.objects.filter(id=sku_id, stock=old_stock).update(stock=new_stock, sales=new_sales)
                    if res == 0:
                        if i==2:
                            transaction.savepoint_rollback(save_id)
                            return JsonResponse({'res': 6, 'errmsg': '提交订单发生冲突'})
                        continue

                    # 添加记录
                    OrderGoods.objects.create(order=order,
                                              sku=sku,
                                              count=int(count),
                                              price=sku.price)

                    # 计算总数目和总价格
                    total_count += int(count)
                    total_price += amount
                    break

        except Exception as e:
            transaction.savepoint_rollback(save_id)
            return JsonResponse({'res': 7, 'errmsg': '订单提交失败'})

        # 更新订单信息表中的总数目和总价格
        order.total_count = total_count
        order.total_price = total_price
        order.save()

        # 删除购物车记录
        conn.hdel(cart_key, *sku_ids)

        # 返回响应
        return JsonResponse({'res': 8, 'msg': '提交订单成功'})


class OrderPayView(View):
    '''支付订单'''
    def post(self, request):
        # 前端: order_id
        # 校验登录
        user = request.user
        if not user.is_authenticated():
            return JsonResponse({'res': 0, 'errmsg': '用户未登录'})

        # 获取数据
        order_id = request.POST.get('order_id')

        # 数据校验
        if not order_id:
            return JsonResponse({'res': 1, 'errmsg': '无效的订单号' })

        try:
            order = OrderInfo.objects.get(order_id=order_id,
                                          user=user,
                                          pay_method=3,
                                          order_status=1)
        except Exception as e:
            return JsonResponse({'res': 2, 'errmsg': '订单不符合支付条件'})

        # 业务处理: 调用支付宝api进行支付
        # 初始化
        # 读取秘钥
        app_private_key_path = os.path.join(settings.BASE_DIR, 'apps', 'order', 'app_private_key.pem')
        alipay_public_key_path = os.path.join(settings.BASE_DIR, 'apps', 'order', 'alipay_public_key.pem')

        with open(app_private_key_path, 'r') as f:
            app_private_key_string = f.read()

        with open(alipay_public_key_path, 'r') as f:
            alipay_public_key_string = f.read()

        alipay = AliPay(
            appid="2016092000556267",
            app_notify_url=None,  # 默认回调url
            app_private_key_string=app_private_key_string,
            # 支付宝的公钥，验证支付宝回传消息使用，不是你自己的公钥,
            alipay_public_key_string=alipay_public_key_string,
            sign_type="RSA2",  # RSA 或者 RSA2
            debug = True  # 默认False
        )

        subject = "天天生鲜%s" % order_id
        total_pay = order.total_price + order.transit_price

        # 电脑网站支付，需要跳转到https://openapi.alipay.com/gateway.do? + order_string
        order_string = alipay.api_alipay_trade_page_pay(
            out_trade_no=order_id,
            total_amount=str(total_pay),
            subject=subject,
            return_url=None,
            notify_url=None  # 可选, 不填则使用默认notify url
        )

        # 返回响应
        pay_url = 'https://openapi.alipaydev.com/gateway.do?' + order_string
        return JsonResponse({'res': 3, 'pay_url': pay_url})


class PayCheckView(View):
    '''支付结果查询'''
    def post(self, request):
        # 登录校验
        user = request.user
        if not user.is_authenticated():
            return JsonResponse({'res': 0, 'errmsg': '用户未登录'})

        # 接收数据
        order_id = request.POST.get('order_id')

        # 数据校验
        if not order_id:
            return JsonResponse({'res': 1, 'errmsg': '无效的订单号'})

        try:
            order = OrderInfo.objects.get(order_id=order_id)
        except OrderInfo.DoesNotExist:
            return JsonResponse({'res': 2, 'errmsg': '订单不存在'})

        # 业务处理: 查询并更改订单状态
        # 初始化
        # 读取秘钥
        app_private_key_path = os.path.join(settings.BASE_DIR, 'apps', 'order', 'app_private_key.pem')
        alipay_public_key_path = os.path.join(settings.BASE_DIR, 'apps', 'order', 'alipay_public_key.pem')

        with open(app_private_key_path, 'r') as f:
            app_private_key_string = f.read()

        with open(alipay_public_key_path, 'r') as f:
            alipay_public_key_string = f.read()

        alipay = AliPay(
            appid="2016092000556267",
            app_notify_url=None,  # 默认回调url
            app_private_key_string=app_private_key_string,
            # 支付宝的公钥，验证支付宝回传消息使用，不是你自己的公钥,
            alipay_public_key_string=alipay_public_key_string,
            sign_type="RSA2",  # RSA 或者 RSA2
            debug=True  # 默认False
        )


        while True:
            response = alipay.api_alipay_trade_query(order_id)
            # 判断订单状态
            code = response.get('code')
            pay_status = response.get('trade_status')
            if code == '10000' and pay_status == 'TRADE_SUCCESS':
                # 支付成功
                # 获取交易码
                trade_no = response.get('trade_no')

                # 更改订单状态
                order.trade_no = trade_no
                order.order_status = 4
                order.save()
                return JsonResponse({'res': 4, 'msg': '支付成功'})

            elif code == '40004' or (code == '10000' and pay_status == 'WAIT_BUYER_PAY'):
                # 等待付款
                import time
                time.sleep(5)
                continue
            else:
                # 交易失败
                return JsonResponse({'res': 3, 'errmsg': '支付失败'})


# /order/comment/order_id
class OrderCommentView(View):
    '''订单商品评价视图'''
    def get(self, request, order_id):
        order = OrderInfo.objects.get(order_id = order_id)
        order.order_status_name = OrderInfo.ORDER_STATUS_DICT[order.order_status]

        order_skus = OrderGoods.objects.filter(order=order)
        for order_sku in order_skus:
            amount = order_sku.price*order_sku.count
            order_sku.amount = amount

        # 组织上下文
        context = {
            'order': order,
            'order_skus': order_skus,
        }

        return render(request, 'order_comment.html', context)
    def post(self, request, order_id):
        # 接收数据
        user = request.user
        if not user.is_authenticated():
            return redirect(reverse('user:user_center_order', kwargs={'page':1}))
        try:
            order = OrderInfo.objects.get(order_id=order_id)
        except OrderInfo.DoesNotExist:
            return redirect(reverse('user:user_center_order', kwargs={'page':1}))

        order_skus = OrderGoods.objects.filter(order=order)
        total_count = len(order_skus)

        # 业务处理: 添加品论, 更改订单状态
        for i in range(1, total_count+1):
            sku_id_name = 'sku_%d' % i
            sku_id = request.POST.get(sku_id_name)

            try:
                order_sku = OrderGoods.objects.get(sku_id=sku_id, order=order)
            except OrderGoods.DoesNotExist:
                continue

            comment_id = 'comment_%d' % i
            comment = request.POST.get(comment_id)

            order_sku.comment = comment
            order_sku.save()

        order.order_status = 5
        order.save()

        # 返回响应
        return redirect(reverse('user:user_center_order', kwargs={'page':1}))




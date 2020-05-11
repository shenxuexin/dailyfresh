from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.http import HttpResponse
from django.views.generic import View
from apps.user.models import User, Address
from apps.goods.models import GoodsSKU
from apps.order.models import OrderInfo, OrderGoods
from django.core.urlresolvers import reverse
from django.conf import settings

from itsdangerous import TimedJSONWebSignatureSerializer as Serialzer, SignatureExpired
from django.core.mail import send_mail
import re
from celery_tasks.tasks import send_register_active_mail
from util.mixin import LoginRequiredMixin
from django_redis import get_redis_connection
from django.core.paginator import Paginator

# Create your views here.
class RegisterView(View):
    '''注册视图类'''
    def get(self, request):
        # 显示页面
        return render(request, 'register.html')

    def post(self, request):
        # 注册处理
        # 数据获取
        username = request.POST.get('user_name')
        password = request.POST.get('pwd')
        email = request.POST.get('email')
        allow = request.POST.get('allow')

        # 数据验证
        # 验证数据完整
        if not all([username, password, email, allow]):
            return render(request, 'register.html', {'errmsg': '数据不完整'})
        # 验证邮箱
        if not re.match(r'^[a-z0-9][\w\.\-]*@[a-z0-9\-]+(\.[a-z]{2,5}){1,2}$', email):
            return render(request, 'register.html', {'errmsg': '邮箱格式不正确'})
        # 验证协议
        if allow != 'on':
            return render(request, 'register.html', {'errmsg': '请同意用户协议'})
        # 验证用户是否已注册
        try:
            user_obj = User.objects.get(username=username)
        except User.DoesNotExist:
            user_obj = None

        if user_obj:
            return render(request, 'register.html', {'errmsg': '用户已存在'})

        # 业务处理
        # 存入数据库
        user = User.objects.create_user(username, email, password)
        user.is_active = 0
        user.save()

        # 加密身份信息:
        serializer = Serialzer('secret_key', 3600)
        info = {'confirm': user.id}
        token = serializer.dumps(info).decode('utf-8')

        # 发送激活邮件
        send_register_active_mail.delay(email, username, token)

        # 返回响应
        return redirect(reverse('goods:index'))


class ActiveView(View):
    '''激活视图类'''
    def get(self, request, token):
        serializer = Serialzer('secret_key', 3600)
        try:
            # 获取用户信息
            info = serializer.loads(token)
            user_id = info['confirm']

            user = User.objects.get(id=user_id)
            user.is_active = 1
            user.save()
            return redirect(reverse('user:login'))
        except SignatureExpired:
            return HttpResponse('用户激活链接已过期')


class LoginView(View):
    '''登录视图类'''
    def get(self, request):
        if 'username' in request.COOKIES:
            username = request.COOKIES.get('username')
            check = 'checked'
        else:
            username = ''
            check = ''
        return render(request, 'login.html', {'username': username, 'check': check})

    def post(self, request):
        # 获取数据
        username = request.POST.get('username')
        password = request.POST.get('pwd')

        # 数据校验
        if not all([username, password]):
            return render(request, 'login.html', {'errmsg': '数据不完整'})

        # 业务处理: 登录校验
        user = authenticate(username=username, password=password)
        if user is not None:
            if user.is_active:
                # 用户已激活
                # 记录用户登录状态
                login(request, user)

                # 获取目标地址
                next_url = request.GET.get('next', reverse('goods:index'))

                # 跳转到目标地址
                response = redirect(next_url)

                # 记住用户名
                remember = request.POST.get('remember')
                if remember == 'on':
                    response.set_cookie('username', username, max_age=7*24*3600)
                else:
                    response.delete_cookie('username')

                return response
            else:
                # 用户未激活
                return render(request, 'login.html', {'errmsg': '账户未激活'})
        else:
            return render(request, 'login.html', {'errmsg': '用户名或密码错误'})


class LogoutView(View):
    '''退出视图类'''
    def get(self, request):
        logout(request)
        return redirect(reverse('goods:index'))


class UserInfoView(LoginRequiredMixin, View):
    '''用户中心信息视图类'''
    def get(self, request):
        # 获取个人信息
        user = request.user
        address = Address.objects.get_default_address(user)

        # 获取最近浏览记录
        # 连接客户端
        conn = get_redis_connection('default')

        # 从redis获取最近浏览的五条商品id
        history_key = 'history_%s' % user.id
        sku_ids = conn.lrange(history_key, 0, 4)

        # 遍历添加商品到列表
        goods_list = list()
        for sku_id in sku_ids:
            goods = GoodsSKU.objects.get(id=sku_id)
            goods_list.append(goods)

        # 构建上下文
        context = {'page': 'info',
                   'address': address,
                   'goods_list': goods_list}

        return render(request, 'user_center_info.html', context)


class UserOrderView(LoginRequiredMixin, View):
    '''用户订单类'''
    def get(self, request, page):
        # 获取个人订单,订单信息,订单商品,小结
        orders = OrderInfo.objects.all().order_by('-order_id')

        for order in orders:
            order_skus = OrderGoods.objects.filter(order=order)

            for order_sku in order_skus:
                amount = order_sku.count*order_sku.price
                order_sku.amount = amount

            order.order_skus = order_skus

            # 获取支付状态
            order_status = order.order_status
            order.order_status_name = OrderInfo.ORDER_STATUS_DICT[order_status]

        # 分页
        paginator = Paginator(orders, 2)

        # 获取页面内容
        try:
            page = int(page)
        except Exception as e:
            page = 1

        if page <=0 or page > paginator.num_pages:
            page = 1

        order_page = paginator.page(page)

        # 显示页码
        all_page = paginator.num_pages
        if all_page < 5:
            page_range = range(1, all_page+1)
        elif page <= 3:
            page_range = range(1, 6)
        elif all_page-page <= 2:
            page_range = range(all_page-4, all_page+1)
        else:
            page_range = range(page-2, page+3)

        # 组织上下文
        context = {
            'order_page': order_page,
            'page_range': page_range,
            'page': 'order'
        }

        return render(request, 'user_center_order.html', context)


class UserSiteView(LoginRequiredMixin, View):
    '''用户地址类'''
    def get(self, request):
        # 获取用户的默认地址
        user = request.user
        address = Address.objects.get_default_address(user)

        return render(request, 'user_center_site.html', {'page': 'site', 'address': address})
    def post(self, request):
        # 获取数据
        user = request.user
        receiver = request.POST.get('receiver')
        addr = request.POST.get('addr')
        zip_code = request.POST.get('zip_code')
        phone = request.POST.get('phone')

        # 校验数据
        # 验证数据是否不完整
        if not all([receiver, addr, phone]):
            return render(request, 'user_center_site.html', {'errmsg': '数据不完整'})
        # 验证手机号是否合法
        if not re.match(r'1[3|4|5|7|8][0-9]{9}', phone):
            return render(request, 'user_center_site.html', {'errmsg': '手机号不合法'})
        # 业务处理: 添加地址
        # 若用户不存在默认地址, 则设置为默认地址,否则不设置为默认地址
        address = Address.objects.get_default_address(user)

        if address:
            is_default = False
        else:
            is_default = True

        Address.objects.create(user=user,
                               receiver=receiver,
                               addr=addr,
                               zip_code=zip_code,
                               phone=phone,
                               is_default=is_default)

        # 返回响应
        return redirect(reverse('user:user_center_site'))

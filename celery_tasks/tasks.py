from celery import Celery
from django.core.mail import send_mail
from django.template import loader
from django.conf import settings
import time
import os

import os
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "dailyfresh_r.settings")
django.setup()

from apps.goods.models import GoodsType, IndexTypeGoodsBanner, IndexGoodsBanner, IndexPromotionBanner

app = Celery('celery_tasks.task', broker='redis://192.168.153.131:6379/4')


@app.task
def send_register_active_mail(email, username, token):
    '''发送邮件'''
    subject = '天天生鲜欢迎邮件'
    msg = ''
    sender = settings.EMAIL_FROM
    receiver = [email]
    html_msg = '<h1>%s, 欢迎您成为天天生鲜注册会员</h1>请点击以下链接激活邮件<br />' \
               '<a href="http://192.168.153.131:8000/user/active/%s">' \
               'http://192.168.153.131:8000/user/active/%s</a>' % (username, token, token)
    send_mail(subject, msg, sender, receiver, html_message=html_msg)

    time.sleep(8)


@app.task
def generate_static_index_page():
    '''生成静态首页'''
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

    # 构建上下文
    context = {
        'types': types,
        'goods_banners': goods_banners,
        'promotion_banners': promotion_banners,
    }

    # 读取模板
    temp = loader.get_template('static_index.html')

    # 渲染模板
    index_html = temp.render(context)

    # 写入文件
    save_path = os.path.join(settings.BASE_DIR, 'static/index.html')
    with open(save_path, 'w') as f:
        f.write(index_html)

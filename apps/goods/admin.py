from django.contrib import admin
from apps.goods.models import GoodsType, IndexTypeGoodsBanner, IndexPromotionBanner, IndexGoodsBanner
from django.core.cache import cache

# Register your models here.
class BaseModelAdmin(admin.ModelAdmin):
    '''基础模型控制类'''
    def save_model(self, request, obj, form, change):
        super(BaseModelAdmin, self).save_model(request, obj, form, change)

        # 生成新的静态页面
        from celery_tasks.tasks import generate_static_index_page
        generate_static_index_page.delay()

        # 删除缓存
        cache.delete('index_page_data')

    def delete_model(self, request, obj):
        super(BaseModelAdmin, self).delete_model(request, obj)

        # 生成新的静态页面
        from celery_tasks.tasks import generate_static_index_page
        generate_static_index_page.delay()

        # 删除缓存
        cache.delete('index_page_data')

class GoodsTypeAdmin(BaseModelAdmin):
    pass


class IndexGoodsBannerAdmin(BaseModelAdmin):
    pass


class IndexTypeGoodsBannerAdmin(BaseModelAdmin):
    pass


class IndexPromotionBannerAdmin(BaseModelAdmin):
    pass


admin.site.register(GoodsType, GoodsTypeAdmin)
admin.site.register(IndexGoodsBanner, IndexGoodsBannerAdmin)
admin.site.register(IndexTypeGoodsBanner, IndexTypeGoodsBannerAdmin)
admin.site.register(IndexPromotionBanner, IndexPromotionBannerAdmin)

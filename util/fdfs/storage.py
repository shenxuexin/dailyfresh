from django.core.files.storage import Storage
from fdfs_client.client import Fdfs_client
from django.conf import settings

class FDFSStorage(Storage):
    '''fdfs 文件存储类'''
    def __init__(self, config_name=None, base_url=None):
        '''将fdfs配置和地址设置为实例属性'''
        if config_name is None:
            config_name = settings.FDFS_CONFIG_FILE
        self.config_name = config_name

        if base_url is None:
            base_url = settings.FDFS_BASE_URL
        self.base_url = base_url

    def _open(self, name, mode='rb'):
        pass

    def _save(self, name, content):
        # 连接fdfs服务器
        client = Fdfs_client(self.config_name)

        # 上传文件
        result = client.upload_by_buffer(content.read())

        # 判断文件上传状态
        # print(result)
        if result.get('Status') != 'Upload successed.':
            raise Exception('上传文件到FDFS失败!')

        # 返回存储的文件名
        filename = result.get('Remote file_id')
        return filename

    def exists(self, name):
        return False

    def url(self, name):
        return self.base_url + name

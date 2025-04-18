import os
import sys
import json
import time
import base64
import hashlib
import random
import urllib.parse
import logging
import requests
import urllib3
import warnings
import webbrowser
import tempfile
import platform
import argparse
from pathlib import Path
from datetime import datetime
from io import BytesIO
from typing import Dict, Any, Optional
from qrcode.main import QRCode
from qrcode.constants import ERROR_CORRECT_L
from qrcode import make as qrcode_make
from PIL import Image



warnings.filterwarnings('ignore')
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
requests.packages.urllib3.disable_warnings()
urllib3.disable_warnings()  


APP_NAME = 'biliraku'
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, 'logs')
os.makedirs(LOG_DIR, exist_ok=True)


USER_CONFIG_DIR = os.path.join(os.path.expanduser('~'), f'.{APP_NAME}')
os.makedirs(USER_CONFIG_DIR, exist_ok=True)


AUTH_FILE = os.path.join(USER_CONFIG_DIR, 'auth.json')
DEEPSEEK_KEY_FILE = os.path.join(USER_CONFIG_DIR, 'deepseek_key.json')
CLOUD_CONFIG_FILE = os.path.join(USER_CONFIG_DIR, 'jfbym_key.json')
CATEGORY_CONFIG_FILE = os.path.join(USER_CONFIG_DIR, 'category_config.json')



CONFIG_FILE = os.path.join(USER_CONFIG_DIR, 'config.json')



PROJECT_CONFIG_FILE = os.path.join(BASE_DIR, 'config.json')


API_CONFIG = {
    'appkey': '783bbb7264451d82',
    'appsec': '2653583c8873dea268ab9386918b1d65',
    'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
}


HEADERS = {
    'User-Agent': API_CONFIG['user_agent'],
    'Content-Type': 'application/x-www-form-urlencoded',
    'Accept': 'application/json',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    'x-bili-metadata-bin': '',
    'x-bili-metadata-buvid': '',
    'x-bili-metadata-device': '',
    'x-bili-metadata-platform': 'pc',
    'x-bili-metadata-env': 'prod',
}


JFBYM_TOKEN = ""
JFBYM_TYPE = "10103"
USE_CLOUD_CAPTCHA = False
AUTO_SELECT_CATEGORY = False
AUTO_CATEGORY_ID = '6'


access_token = None
csrf = None
API_KEY_DEEPSEEK = None
login_count = 0


PROMPT = """当前时间：{}

你是一个高效、精准的答题专家。面对选择题时，请根据题目和选项判断最可能的正确答案，并仅返回对应选项的序号（1、2、3、4）。

示例：
问题：中国第一位皇帝是谁？
选项：['秦始皇', '汉武帝', '唐太宗', '刘邦']
回答：1

如果不能完全确定答案，请选择最接近正确的选项，并返回其序号。不提供额外解释，也不输出 1–4 之外的内容。

---

请回答以下问题：
{}
"""


def setup_logger(name=APP_NAME):
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)


    os.makedirs(LOG_DIR, exist_ok=True)


    log_file = os.path.join(LOG_DIR, f'{datetime.now().strftime("%Y-%m-%d_%H-%M-%S")}.log')
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.INFO)


    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)


    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)


    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


logger = setup_logger()



session = requests.Session()
session.verify = False
session.mount('http://', requests.adapters.HTTPAdapter(
    max_retries=urllib3.util.retry.Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[500, 502, 503, 504]
    )
))
session.mount('https://', requests.adapters.HTTPAdapter(
    max_retries=urllib3.util.retry.Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[500, 502, 503, 504]
    )
))


appkey = API_CONFIG['appkey']
appsec = API_CONFIG['appsec']
headers = HEADERS.copy()

def appsign(params):

    try:
        params.update({'ts': str(int(time.time()))})
        params.update({'appkey': appkey})
        params = dict(sorted(params.items()))
        query = urllib.parse.urlencode(params)
        sign = hashlib.md5((query+appsec).encode()).hexdigest()
        params.update({'sign':sign})
        return params
    except Exception as e:
        logger.error(f'生成签名失败: {str(e)}')
        raise

def get(url, params=None):
    global headers, access_token, session

    
    current_headers = headers.copy()
    if access_token:
        current_headers.update({
            'Authorization': f'Bearer {access_token}'
        })

    try:
        logger.debug(f"GET请求: {url}")
        if params:
            logger.debug(f"参数: {params}")

        response = session.get(url, headers=current_headers, params=params, verify=False)
        response.raise_for_status()
        
        response_json = response.json()
        return response_json
    except Exception as e:
        logger.error(f"GET请求失败: {str(e)}")
        return {'code': -1, 'message': str(e)}


def post(url, data=None, json=None):
    global headers, access_token, session

    
    current_headers = headers.copy()
    if access_token:
        current_headers.update({
            'Authorization': f'Bearer {access_token}'
        })

    try:
        logger.debug(f"POST请求: {url}")
        if data:
            logger.debug(f"表单数据: {data}")
        if json:
            logger.debug(f"JSON数据: {json}")

        response = session.post(url, headers=current_headers, data=data, json=json, verify=False)
        response.raise_for_status()
        
        response_json = response.json()
        return response_json
    except Exception as e:
        logger.error(f"POST请求失败: {str(e)}")
        return {'code': -1, 'message': str(e)}


def load_api_key():

    if os.path.exists(DEEPSEEK_KEY_FILE):
        try:
            with open(DEEPSEEK_KEY_FILE, 'r') as f:
                data = json.load(f)
                return data.get('api_key', '')
        except Exception as e:
            logger.error(f'读取DeepSeek API密钥失败: {str(e)}')
    return ''

def save_api_key(api_key):

    try:
        with open(DEEPSEEK_KEY_FILE, 'w') as f:
            json.dump({'api_key': api_key}, f)
        logger.info('DeepSeek API密钥已保存')
    except Exception as e:
        logger.error(f'保存DeepSeek API密钥失败: {str(e)}')

def load_auth_data():
    
    if os.path.exists(AUTH_FILE):
        try:
            file_mtime = os.path.getmtime(AUTH_FILE)
            current_time = time.time()
            if (current_time - file_mtime) > 7 * 24 * 3600:
                logger.info('认证信息已过期（超过7天），需要重新登录')
                return False
                
            with open(AUTH_FILE, 'r') as f:
                auth_data = json.load(f)
                
                if 'access_token' in auth_data:
                    global access_token, csrf
                    access_token = auth_data['access_token']
                    
                    csrf = auth_data.get('csrf', '')
                    
                    
                    if 'mid' in auth_data:
                        headers.update({
                            'x-bili-mid': auth_data['mid'],
                        })
                    
                    
                    if 'cookie' in auth_data and auth_data['cookie']:
                        headers.update({
                            'cookie': auth_data['cookie']
                        })
                        
                    logger.info('已从缓存加载登录信息')
                    return True
        except Exception as e:
            logger.error(f'读取认证信息失败: {str(e)}')
    return False

def check_auth():
    
    global access_token
    
    
    if access_token:
        logger.info("本地已有登录状态，验证中...")
        return True
    
    
    if load_auth_data():
        return True
    
    logger.info("未检测到登录状态，需要重新登录")
    return False

def save_auth_data(auth_data):
    
    try:
        
        if 'access_token' not in auth_data or not auth_data['access_token']:
            logger.error("认证数据缺少access_token，无法保存")
            return False
        
        
        if 'mid' not in auth_data or not auth_data['mid']:
            auth_data['mid'] = '0'
            logger.warning("认证数据缺少mid，将使用默认值")
        
        
        if 'csrf' not in auth_data:
            auth_data['csrf'] = ''
            logger.warning("认证数据缺少csrf，将使用空值")
            
        
        if 'cookie' not in auth_data:
            auth_data['cookie'] = ''
            logger.warning("认证数据缺少cookie，将使用空值")
                
        
        with open(AUTH_FILE, 'w') as f:
            json.dump(auth_data, f, indent=4)
        logger.info('认证信息已保存到缓存')
        return True
    except Exception as e:
        logger.error(f'保存认证信息失败: {str(e)}')
        return False


class DeepSeekAPI:
    def __init__(self):
        self.base_url = "https://api.deepseek.com/v1"
        self.model = "deepseek-chat"
        self.api_key = API_KEY_DEEPSEEK

    def ask(self, question: str, timeout: Optional[int] = 30) -> str:
        url = f"{self.base_url}/chat/completions"
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        
        data = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": PROMPT.format(time.time(), question)
                }
            ]
        }

        try:
            response = requests.post(
                url,
                headers=headers,
                json=data,
                timeout=timeout,
                verify=False  
            )
            

            if response.status_code == 400:
                logger.error(f"DeepSeek API错误 (400): {response.text}")
                raise Exception("DeepSeek API返回400错误")
            elif response.status_code != 200:
                logger.error(f"DeepSeek API错误 ({response.status_code}): {response.text}")
                raise Exception(f"DeepSeek API请求失败: HTTP {response.status_code}")
                
            return response.json()["choices"][0]["message"]["content"]
        except requests.exceptions.RequestException as e:
            logger.error(f"DeepSeek API网络请求失败: {str(e)}")
            raise Exception(f"DeepSeek API请求失败: {str(e)}")
        except (KeyError, IndexError) as e:
            logger.error(f"DeepSeek API返回格式错误: {str(e)}")
            raise Exception(f"DeepSeek API返回解析失败: {str(e)}")
        except Exception as e:
            logger.error(f"DeepSeek API未知错误: {str(e)}")
            raise 


def download_captcha_image(url):

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://www.bilibili.com/',
        'Accept': 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Connection': 'keep-alive'
    }
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            
            response = requests.get(url, headers=headers, timeout=10, verify=False)
            if response.status_code == 200:
                return response.content
            elif response.status_code == 412:

                logger.warning(f"下载验证码被拒绝 (状态码: 412)，尝试重试 {attempt+1}/{max_retries}")

                headers['User-Agent'] += f' {random.randint(1000, 9999)}'
                time.sleep(random.uniform(1.0, 3.0))
            else:
                logger.warning(f"下载验证码失败，状态码: {response.status_code}，尝试重试 {attempt+1}/{max_retries}")
                time.sleep(1)
        except Exception as e:
            logger.warning(f"下载验证码出错: {str(e)}，尝试重试 {attempt+1}/{max_retries}")
            time.sleep(1)
    
    logger.error("多次尝试下载验证码失败")
    return None

def recognize_with_jfbym(image_data):

    if not JFBYM_TOKEN:
        logger.error("缺少云码API token配置")
        return None
    
    try:
        
        base64_data = base64.b64encode(image_data).decode('utf-8')
        
        
        api_url = "http://api.jfbym.com/api/YmServer/customApi"
        
        
        data = {
            "token": JFBYM_TOKEN,
            "type": JFBYM_TYPE,
            "image": base64_data,
        }
        
        headers = {
            "Content-Type": "application/json"
        }
        
        logger.info(f"请求云码API，类型ID: {JFBYM_TYPE}")
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                
                proxies = {
                    "http": None,
                    "https": None
                }
                logger.info("已禁用代理设置，直接连接到云码API服务器")
                
                
                response = requests.post(
                    api_url, 
                    headers=headers, 
                    json=data, 
                    timeout=15, 
                    verify=False,
                    proxies=proxies  
                )
                
                logger.info(f"云码API响应状态码: {response.status_code}")
                
                if response.status_code == 200:
                    
                    logger.info(f"云码API完整响应: {response.text}")
                    
                    result = response.json()
                    logger.info(f"云码API响应JSON: {result}")
                    
                    
                    if result.get('code') == 10000:
                        
                        if ('data' in result and 
                            isinstance(result['data'], dict) and 
                            'data' in result['data']):
                            captcha_text = result['data']['data']
                            logger.info(f"云码识别成功：{captcha_text}")
                            return captcha_text
                        else:
                            logger.warning("云码API返回成功，但未找到验证码结果")
                            logger.info("请检查API响应结构，验证码应位于data.data字段")
                    else:
                        error_msg = result.get('message', result.get('msg', '未知错误'))
                        logger.warning(f"云码API返回错误: 代码={result.get('code')}, 信息={error_msg}")
                else:
                    logger.warning(f"云码API请求失败，状态码: {response.status_code}")
                    logger.warning(f"响应内容: {response.text}")
                
                if attempt < max_retries - 1:
                    logger.info(f"尝试重试 ({attempt+1}/{max_retries})")
                    time.sleep(random.uniform(1.0, 3.0))
            
            except Exception as e:
                logger.warning(f"云码API请求出错: {str(e)}")
                import traceback
                logger.debug(f"错误详情: {traceback.format_exc()}")
                if attempt < max_retries - 1:
                    time.sleep(1)
        
        logger.error("多次尝试云码API识别验证码失败")
        return None
        
    except Exception as e:
        logger.error(f"处理验证码图片出错: {str(e)}")
        import traceback
        logger.error(f"错误详情: {traceback.format_exc()}")
        return None

def recognize_captcha(captcha_url, cloud_api=True):

    try:

        if not cloud_api:
            logger.info("将在浏览器中打开验证码以供手动输入")
            webbrowser.open(captcha_url)
            return None
        

        logger.info("正在下载验证码图片...")
        image_data = download_captcha_image(captcha_url)
        
        if not image_data:
            logger.warning("无法下载验证码图片，将在浏览器中打开")
            webbrowser.open(captcha_url)
            return None
        

        logger.info("使用云码API识别验证码...")
        captcha_text = recognize_with_jfbym(image_data)
        
        if captcha_text:
            logger.info(f"验证码识别成功: {captcha_text}")
            return captcha_text
        

        logger.warning("云API识别失败，将在浏览器中打开验证码")
        webbrowser.open(captcha_url)
        return None
        
    except Exception as e:
        logger.error(f"验证码识别过程出错: {str(e)}")

        try:
            webbrowser.open(captcha_url)
        except:
            logger.error("无法打开浏览器，请手动复制链接查看验证码")
        return None


def category_get():
    
    try:
        
        if not access_token:
            logger.error("获取分类时发现未登录，请先完成登录")
            return None
            
        params = {
            'access_key': access_token,
            'csrf': csrf,
            'disable_rcmd': 0,
            'mobi_app': 'android',
            'platform': 'android',
            'statistics': '{"appId":1,"platform":3,"version":"8.40.0","abtest":""}',
            'web_location': '333.790'
        }
        
        res = get('https://api.bilibili.com/x/senior/v1/category', params)
        
        if res and res.get('code') == 0:
            return res.get('data')
        elif res and res.get('code') == 41099:
            logger.error(f'获取分类失败，可能是已经达到答题限制(B站每日限制3次)，请前往B站APP确认是否可以正常答题: {res}')
            return None
        elif res and res.get('code') == -101:
            logger.error(f'获取分类失败，账号未登录错误，可能需要重新登录或刷新token: {res}')
            return None
        else:
            logger.error(f'获取分类失败，请前往B站APP确认是否可以正常答题: {res}')
            return None
    except Exception as e:
        logger.error(f"获取分类出错: {str(e)}")
        return None

def captcha_get():
    
    try:
        
        if not access_token:
            logger.error("获取验证码时发现未登录，请先完成登录")
            return None
    
        params = {
            'access_key': access_token,
            'csrf': csrf,
            'disable_rcmd': 0,
            'mobi_app': 'android',
            'platform': 'android',
            'statistics': '{"appId":1,"platform":3,"version":"8.40.0","abtest":""}',
            'web_location': '333.790'
        }
        
        res = get('https://api.bilibili.com/x/senior/v1/captcha', params)
        
        if res and res.get('code') == 0:
            return res.get('data')
        else:
            error_msg = res.get('message', '未知错误') if res else '请求失败'
            logger.error(f"获取验证码失败: {error_msg}")
            return None
    except Exception as e:
        logger.error(f"获取验证码出错: {str(e)}")
        return None

def captcha_submit(code, captcha_token, ids):
    
    try:
        if not access_token:
            logger.error("提交验证码时发现未登录，请先完成登录")
            return False
            
        params = {
            "access_key": access_token,
            "bili_code": code,
            "bili_token": captcha_token,
            "csrf": csrf,
            "disable_rcmd": "0",
            "gt_challenge": "",
            "gt_seccode": "",
            "gt_validate": "",
            "ids": ids,
            "mobi_app": "android",
            "platform": "android",
            "statistics": "{\"appId\":1,\"platform\":3,\"version\":\"8.40.0\",\"abtest\":\"\"}",
            "type": "bilibili",
        }
        
        res = post('https://api.bilibili.com/x/senior/v1/captcha/submit', params)
        
        if res and res.get('code') == 0:
            logger.info("验证码提交成功")
            return True
        else:
            error_msg = res.get('message', '未知错误') if res else '请求失败'
            logger.error(f"提交验证码失败: {error_msg}")
            return False
    except Exception as e:
        logger.error(f"提交验证码出错: {str(e)}")
        return False

def question_get():
    
    return get('https://api.bilibili.com/x/senior/v1/question', {
        "access_key": access_token,
        "csrf": csrf,
        "disable_rcmd": "0",
        "mobi_app": "android",
        "platform": "android",
        "statistics": "{\"appId\":1,\"platform\":3,\"version\":\"8.40.0\",\"abtest\":\"\"}",
        "web_location": "333.790",
    })

def question_submit(id, ans_hash, ans_text):
    
    return post('https://api.bilibili.com/x/senior/v1/answer/submit', {
        "access_key": access_token,
        "csrf": csrf,
        "id": id,
        "ans_hash": ans_hash,
        "ans_text": ans_text,
        "disable_rcmd": "0",
        "mobi_app": "android",
        "platform": "android",
        "statistics": "{\"appId\":1,\"platform\":3,\"version\":\"8.40.0\",\"abtest\":\"\"}",
        "web_location": "333.790",
    })

def question_result():
    
    res = get('https://api.bilibili.com/x/senior/v1/answer/result', {
        "access_key": access_token,
        "csrf": csrf,
        "disable_rcmd": "0",
        "mobi_app": "android",
        "platform": "android",
        "statistics": "{\"appId\":1,\"platform\":3,\"version\":\"8.40.0\",\"abtest\":\"\"}",
        "web_location": "333.790",
    })
    if res and res.get('code') == 0:
        return res.get('data')
    else:
        raise Exception('答题结果获取失败{}'.format(res))


def getTicket():
    ts = int(time.time())
    payload = f"ts={ts}&sign_method=HMAC-SHA1"
    
    
    try:
        md5hash = hashlib.md5(f"api.bilibili.com/x/internal/oauth2/getHTTPTicket{ts}".encode()).hexdigest()
        return f"{md5hash},{ts}"
    except Exception as e:
        logger.error(f"生成ticket失败: {str(e)}")
        
        fallback_hash = hashlib.md5(f"bilibili{ts}".encode()).hexdigest()
        return f"{fallback_hash},{ts}"

def qrcode_get():
    
    logger.debug("调用qrcode_get获取登录二维码")
    try:
        
        params = {
            'local_id': str(int(time.time())),
            'app_id': '1',  
        }
        
        
        signed_params = appsign(params.copy())
        logger.debug(f"请求参数(已签名): {signed_params}")
        
        
        custom_headers = {
            'User-Agent': API_CONFIG['user_agent'],
            'Content-Type': 'application/x-www-form-urlencoded',
            'Accept': 'application/json',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        }
        
        url = 'https://passport.bilibili.com/x/passport-tv-login/qrcode/auth_code'
        
        
        response = requests.post(
            url=url,
            data=signed_params,
            headers=custom_headers,
            timeout=10,
            verify=False
        )
        
        logger.debug(f"二维码API请求状态码: {response.status_code}")
        
        
        if response.status_code != 200:
            logger.error(f"二维码获取失败: HTTP状态码 {response.status_code}")
            logger.error(f"响应内容: {response.text[:500]}")
            return {'code': -1, 'message': f'HTTP错误: {response.status_code}', 'data': {}}
        
        
        try:
            json_resp = response.json()
            logger.debug(f"二维码获取返回: {json_resp}")
            
            
            if json_resp.get('code') != 0:
                error_msg = json_resp.get('message', '未知错误')
                logger.error(f"二维码获取失败: {error_msg}")
                return json_resp
            
            
            return json_resp
            
        except ValueError as e:
            logger.error(f"二维码接口返回非JSON数据: {str(e)}")
            logger.error(f"原始响应内容: {response.text[:500]}...")
            return {'code': -1, 'message': '接口返回格式错误', 'data': {}}
        
    except requests.exceptions.RequestException as e:
        logger.error(f"获取二维码网络请求失败: {str(e)}")
        import traceback
        logger.error(f"请求异常详情: {traceback.format_exc()}")
        return {'code': -1, 'message': f'请求错误: {str(e)}', 'data': {}}
    except Exception as e:
        logger.error(f"获取二维码时发生异常: {str(e)}")
        import traceback
        logger.error(f"异常详情: {traceback.format_exc()}")
        return {'code': -1, 'message': str(e), 'data': {}}

def qrcode_poll(auth_code):
    
    logger.debug(f"调用qrcode_poll检查二维码状态 auth_code={auth_code}")
    
    try:
        
        params = {
            'auth_code': auth_code,
            'app_id': '1',  
            'local_id': str(int(time.time())),  
        }
        
        
        signed_params = appsign(params.copy())
        logger.debug(f"轮询请求参数(已签名): {signed_params}")
        
        
        custom_headers = {
            'User-Agent': API_CONFIG['user_agent'],
            'Content-Type': 'application/x-www-form-urlencoded',
            'Accept': 'application/json',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        }
        
        url = 'https://passport.bilibili.com/x/passport-tv-login/qrcode/poll'
        
        
        response = requests.post(
            url=url,
            data=signed_params,
            headers=custom_headers,
            timeout=15,  
            verify=False
        )
        
        logger.debug(f"二维码轮询状态码: {response.status_code}")
        logger.debug(f"请求URL: {url}")
        logger.debug(f"请求参数: {signed_params}")
        
        
        if response.status_code != 200:
            logger.error(f"二维码状态获取失败: HTTP状态码 {response.status_code}")
            logger.error(f"响应内容: {response.text[:500]}")
            return {'code': -1, 'message': f'HTTP错误: {response.status_code}', 'data': {}}
        
        
        try:
            
            logger.debug(f"原始响应: {response.text}")
            
            json_resp = response.json()
            logger.debug(f"二维码状态轮询返回: {json_resp}")
            
            
            return json_resp
            
        except ValueError as e:
            logger.error(f"二维码状态接口返回非JSON数据: {str(e)}")
            logger.error(f"原始响应内容: {response.text[:500]}...")
            return {'code': -1, 'message': '接口返回格式错误', 'data': {}}
        
    except requests.exceptions.RequestException as e:
        logger.error(f"轮询二维码状态网络请求失败: {str(e)}")
        import traceback
        logger.error(f"请求异常详情: {traceback.format_exc()}")
        return {'code': -1, 'message': f'请求错误: {str(e)}', 'data': {}}
    except Exception as e:
        logger.error(f"轮询二维码状态时发生异常: {str(e)}")
        import traceback
        logger.error(f"异常详情: {traceback.format_exc()}")
        return {'code': -1, 'message': str(e), 'data': {}}

def save_qrcode_image(url):
    
    try:
        
        if not url:
            logger.error("无法生成二维码: URL为空")
            return None
            
        
        try:
            qr_img = qrcode_make(url)
        except Exception as e:
            logger.error(f"生成二维码图像失败: {str(e)}")
            return None

        
        temp_dir = Path(tempfile.gettempdir()) / APP_NAME
        os.makedirs(temp_dir, exist_ok=True)

        
        qr_path = temp_dir / "bili_qrcode.png"
        try:
            qr_img.save(qr_path)
            logger.info(f"二维码图片已保存到: {qr_path}")
        except Exception as e:
            logger.error(f"保存二维码图片失败: {str(e)}")
            return None

        
        try:
            if platform.system() == "Darwin":  
                os.system(f"open {qr_path}")
            elif platform.system() == "Windows":
                os.system(f"start {qr_path}")
            elif platform.system() == "Linux":
                os.system(f"xdg-open {qr_path}")
            logger.info("已自动打开二维码图片")
        except Exception as e:
            logger.info(f"无法自动打开图片，请手动查看保存的二维码图片: {qr_path}")
            
        return str(qr_path)
    except Exception as e:
        logger.error(f"保存二维码图片过程中出错: {str(e)}")
        return None


def auth():
    
    global access_token, csrf, login_count
    
    
    if check_auth():
        return True
    
    
    login_count += 1

    
    logger.info("开始B站TV端登录流程...")
    retry_count = 0
    qr_data = None
    
    
    while retry_count < 3:
        qr_response = qrcode_get()
        
        if qr_response.get('code') == 0:
            qr_data = qr_response.get('data', {})
            if qr_data and qr_data.get('url') and qr_data.get('auth_code'):
                break
        
        retry_count += 1
        logger.warning(f"获取二维码失败，{retry_count}/3次重试")
        time.sleep(1)
    
    
    if not qr_data or not qr_data.get('url') or not qr_data.get('auth_code'):
        logger.error("无法获取登录二维码，请检查网络连接")
        return False
    
    
    auth_code = qr_data.get('auth_code')
    qr_url = qr_data.get('url')
    logger.info(f"获取二维码成功，请扫描二维码登录")
    logger.info(f"二维码URL: {qr_url}")
    logger.info(f"认证码: {auth_code}")
    save_qrcode_image(qr_url)
    
    
    logger.info("等待扫码...")
    polling_count = 0
    max_polling = 90  
    
    
    last_code = None
    
    while polling_count < max_polling:
        polling_count += 1
        logger.info(f"轮询次数: {polling_count}/{max_polling}")
        
        
        try:
            poll_response = qrcode_poll(auth_code)
            
            
            import json
            logger.debug(f"原始响应: {json.dumps(poll_response, ensure_ascii=False)}")
            
            
            response_code = poll_response.get('code', -1)
            response_message = poll_response.get('message', '未知状态')
            poll_data = poll_response.get('data', {})
            
            
            if response_code != last_code:
                logger.info(f"扫码状态变化: code={response_code}, message={response_message}")
                last_code = response_code
            
            
            if poll_data and 'access_token' in poll_data:
                access_token = poll_data.get('access_token')
                refresh_token = poll_data.get('refresh_token', '')
                logger.info(f"发现access_token: {access_token[:10]}...")
                
                
                auth_data = {
                    'access_token': access_token,
                    'refresh_token': refresh_token,
                    'cookie': '',  
                    'csrf': '',    
                    'uid': '',     
                    'timestamp': int(time.time())
                }
                save_auth_data(auth_data)
                
                logger.info("成功获取到access_token，立即返回True")
                return True
                
            
            if response_code == 0:
                logger.info("收到成功状态码，但未找到access_token，检查响应内容...")
                logger.info(f"完整响应内容: {poll_response}")
                
                
                for key, value in poll_data.items():
                    logger.info(f"数据字段: {key} = {value}")
                
                
                logger.warning("API可能已变更，请查看日志并报告问题")
                
            
            elif response_code == 86038:
                logger.error("二维码已失效，请重新获取")
                return False
            elif response_code == 86039:
                
                pass  
            elif response_code == 86090:
                
                pass  
            elif response_code == 86101:
                
                pass  
            else:
                
                logger.warning(f"未知状态码: {response_code}, 消息: {response_message}")
                
        except Exception as e:
            import traceback
            logger.error(f"轮询过程发生错误: {str(e)}")
            logger.error(f"错误详情: {traceback.format_exc()}")
        
        
        if response_code in [86039, 86090]:  
            time.sleep(1)  
        else:
            time.sleep(2)  
    
    logger.error("二维码扫描超时，请重试")
    return False


class QuizSession:
    def __init__(self):
        self.question_id = None
        self.answers = None
        self.question_num = 0
        self.question = None
        self.total_questions = 0
        self.answered_questions = 0

    def start(self):
    
        try:
            logger.info("开始答题流程，请耐心等待完成所有题目...")

            answered_count = 0
            max_questions = 200
            

            while answered_count < max_questions:
                if not self.get_question():
                    logger.error("获取题目失败")
                    break
                

                self.answered_questions += 1
                answered_count += 1
                

                self.display_question()
                
                try:
                    llm = DeepSeekAPI()
                    answer = llm.ask(self.get_question_prompt())
                    logger.info('AI给出的答案:{}'.format(answer))
                    
                    try:
                        answer = int(answer)
                        if not (1 <= answer <= len(self.answers)):
                            logger.warning(f"无效的答案序号: {answer}")
                            logger.warning("DeepSeek返回了无效答案，随机选择一个答案并继续...")
                            answer = random.randint(1, len(self.answers))
                            logger.info(f"随机选择了答案: {answer}")
                    except ValueError:
                        logger.warning("AI回复了无关内容:[{}],正在重试".format(answer))
                        logger.warning("DeepSeek回复了无关内容，随机选择一个答案并继续...")
                        answer = random.randint(1, len(self.answers))
                        logger.info(f"随机选择了答案: {answer}")
                except Exception as e:
                    logger.error(f"AI请求出错: {str(e)}")
                    logger.warning("DeepSeek请求失败，随机选择一个答案并继续...")
                    answer = random.randint(1, len(self.answers))
                    logger.info(f"随机选择了答案: {answer}")

                result = self.answers[answer-1]
                submit_result = self.submit_answer(result)
                

                if not submit_result:
                    logger.info("答题流程结束")
                    break
            

            if answered_count >= max_questions:
                logger.warning(f"已回答 {answered_count} 题，达到设定的最大题数限制")
                
            logger.info(f"本次共回答了 {answered_count} 道题目")
            self.print_result()
        except KeyboardInterrupt:
            logger.info("答题会话已终止")
            logger.info(f"本次共回答了 {self.answered_questions} 道题目")
            self.print_result()
        except Exception as e:
            logger.error(f"答题过程发生错误: {str(e)}")
            logger.info(f"本次共回答了 {self.answered_questions} 道题目")
            self.print_result()

    def get_question(self):
    
        try:
            question = question_get()
            if not question:
                return False

            if question.get('code') != 0:
                logger.info("需要验证码验证")
                return self.handle_verification()

            data = question.get('data', {})
            self.question = data.get('question')
            self.answers = data.get('answers', [])
            self.question_id = data.get('id')
            self.question_num = data.get('question_num', 0)
            return True

        except Exception as e:
            logger.error(f"获取题目失败: {str(e)}")
            return False

    def handle_verification(self):
        try:
            logger.info("获取分类信息...")
            category = category_get()
            
            
            if not category:
                logger.warning("无法自动获取分类，将使用默认分类或手动选择")
                
                
                if AUTO_SELECT_CATEGORY:
                    ids = AUTO_CATEGORY_ID
                    logger.info(f"使用配置的默认分类: 文史类 (ID: {ids})")
                else:
                    logger.info("请选择分类:")
                    logger.info("[1] 文史类 (ID: 6) - 推荐")
                    logger.info("[2] 理工类 (ID: 8)")
                    logger.info("[3] 艺术类 (ID: 7)")
                    logger.info("[4] 财经类 (ID: 9)")
                    
                    
                    category_choice = input('请选择分类 [默认1]: ').strip() or '1'
                    category_map = {'1': '6', '2': '8', '3': '7', '4': '9'}
                    ids = category_map.get(category_choice, '6')
                    logger.info(f"已选择: ID {ids}")
            else:
                
                ids = AUTO_CATEGORY_ID if AUTO_SELECT_CATEGORY else '6'
                logger.info(f"已自动选择: 文史类 (ID: {ids})")
            
            logger.info("获取验证码...")
            captcha_res = captcha_get()
            if not captcha_res:
                logger.error("获取验证码失败，请确认登录状态")
                return False
                
            captcha_url = captcha_res.get('url')
            logger.info(f"验证码链接: {captcha_url}")
            
            captcha = None
            
            if USE_CLOUD_CAPTCHA:
                try:
                    logger.info("正在使用云码API自动识别验证码...")
                    captcha = recognize_captcha(captcha_url, cloud_api=True)
                    
                    if captcha:
                        logger.info(f"云码识别成功，将自动使用结果: {captcha}")
                except Exception as e:
                    logger.error(f"自动识别验证码出错: {str(e)}")
                    captcha = None
            
            if not captcha:
                if not webbrowser.open(captcha_url):
                    logger.warning("无法自动打开浏览器，请手动复制链接查看验证码")
                logger.info(f"请查看浏览器中的验证码并输入 (链接: {captcha_url})")
                captcha = input('请输入验证码: ')
            
            logger.info(f"正在提交验证码: {captcha}, 分类ID: {ids}")
            
            max_retries = 3
            retry_count = 0
            
            while retry_count < max_retries:
                try:
                    
                    captcha_token = captcha_res.get('token')
                    if captcha_submit(code=captcha, captcha_token=captcha_token, ids=ids):
                        logger.info("验证通过✅")
                        return self.get_question()
                    else:
                        retry_count += 1
                        if retry_count >= max_retries:
                            logger.error("验证失败")
                            retry_choice = input('是否重试? [1]是 [2]否: ')
                            if retry_choice == '1':
                                return self.handle_verification()
                            return False
                        else:
                            logger.warning(f"验证失败，正在重试 ({retry_count}/{max_retries})...")
                            if retry_count == 2:
                                logger.info("多次重试失败，尝试手动输入验证码...")
                                if not webbrowser.open(captcha_url):
                                    logger.warning("无法自动打开浏览器，请手动复制链接查看验证码")
                                logger.info(f"请查看浏览器中的验证码并输入 (链接: {captcha_url})")
                                captcha = input('请输入验证码: ')
                            time.sleep(2)
                except Exception as e:
                    retry_count += 1
                    logger.error(f"提交验证码失败: {str(e)}")
                    if retry_count >= max_retries:
                        retry_choice = input('是否重试? [1]是 [2]否: ')
                        if retry_choice == '1':
                            return self.handle_verification()
                        return False
                    else:
                        logger.warning(f"验证码提交出错: {str(e)}，正在重试 ({retry_count}/{max_retries})...")
                        time.sleep(2)
            
            return False
        except Exception as e:
            logger.error(f"处理验证码验证时出错: {str(e)}")
            return False

    def display_question(self):
    
        logger.info(f"正在作答第 {self.question_num} 题")
        logger.info(f"题目: {self.question}")
        for i, answer in enumerate(self.answers, 1):
            logger.info(f"选项{i}: {answer['ans_text']}")

    def get_question_prompt(self):
    
        options = [f"{ans['ans_text']}" for ans in self.answers]
        return f"问题：{self.question}\n选项：{options}"

    def submit_answer(self, answer):
    
        try:
            if not self.question_id or not answer:
                logger.error("题目ID或答案不能为空")
                return False
            
            ans_hash = answer.get('ans_hash')
            ans_text = answer.get('ans_text')
            
            logger.info(f"正在提交答案: {ans_text} (hash: {ans_hash})")
            result = question_submit(self.question_id, ans_hash, ans_text)
            
            if result.get('code') == 0:
                data = result.get('data', {})
                

                if 'is_correct' in data and 'is_last' in data:
                    is_correct = data.get('is_correct')
                    is_last = data.get('is_last')
                    correct_text = "✓ 正确" if is_correct else "✗ 错误"
                    
                    if 'correct_answer' in data and not is_correct:
                        correct_answer = data.get('correct_answer', {})
                        logger.info(f"提交结果: {correct_text}，正确答案: {correct_answer.get('ans_text')}")
                    else:
                        logger.info(f"提交结果: {correct_text}")
                    

                    if is_last:
                        logger.info("已完成所有题目")
                        return False
                

                elif 'correct' in data:
                    correct = data.get('correct')
                    logger.info(f"提交结果: {'✓ 正确' if correct else '✗ 错误'}")
                    
                    if not correct and 'correct_answer' in data:
                        correct_answer = data.get('correct_answer', {})
                        if isinstance(correct_answer, dict) and 'ans_text' in correct_answer:
                            logger.info(f"正确答案: {correct_answer.get('ans_text')}")
            
                return True
            
            elif result.get('code') == 41109:

                logger.info("答题已结束")
                return False
            
            else:
                logger.error(f"答案提交失败，错误码: {result.get('code')}, 信息: {result.get('message')}")
                return False
            
        except Exception as e:
            logger.error(f"提交答案时出错: {str(e)}")
            return False

    def print_result(self):
    
        try:
            result = question_result()
            if result:
                total_score = result.get('score', 0)
                logger.info(f"最终得分: {total_score}")
                
                if 'scores' in result:
                    logger.info("分类得分详情:")
                    for score_item in result.get('scores', []):
                        category = score_item.get('category', '未知')
                        score = score_item.get('score', 0)
                        total = score_item.get('total', 0)
                        logger.info(f"  {category}: {score}/{total}")
                
                if total_score >= 60:
                    logger.info("🎉 恭喜, 答题通过!")
                else:
                    logger.info("😢 很遗憾, 答题未通过，请重新尝试。")
                    logger.info("提示: 尝试选择不同的分类可能会提高通过率。")
            
        except Exception as e:
            logger.error(f"获取答题结果时出错: {str(e)}")


def clear_user_data(force=False):
    
    global access_token, csrf, JFBYM_TOKEN, API_KEY_DEEPSEEK, USE_CLOUD_CAPTCHA, AUTO_SELECT_CATEGORY
    
    files_to_remove = []
    
    
    if os.path.exists(AUTH_FILE):
        files_to_remove.append(AUTH_FILE)
    
    if not force:  
        access_token = None
        csrf = None
        logger.info("已清除登录状态，将重新获取二维码登录")
        return
        
    
    config_files = [
        AUTH_FILE,
        DEEPSEEK_KEY_FILE,
        CLOUD_CONFIG_FILE,
        CATEGORY_CONFIG_FILE
    ]
    
    for file_path in config_files:
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                logger.info(f"已删除配置文件: {file_path}")
            except Exception as e:
                logger.error(f"删除文件 {file_path} 失败: {str(e)}")
    
    
    access_token = None
    csrf = None
    API_KEY_DEEPSEEK = None
    JFBYM_TOKEN = ""
    USE_CLOUD_CAPTCHA = False
    AUTO_SELECT_CATEGORY = False
    
    logger.info("所有用户数据已清除，将重新进行完整设置")


def get_user_info():
    
    try:
        
        url = 'https://api.bilibili.com/x/web-interface/nav'
        
        response = session.get(
            url,
            headers={
                'User-Agent': API_CONFIG['user_agent'],
                'Referer': 'https://www.bilibili.com/'
            },
            verify=False
        )
        
        
        if response.status_code != 200:
            logger.error(f"获取用户信息失败: HTTP状态码 {response.status_code}")
            return {'code': -1, 'message': f'HTTP错误 {response.status_code}'}
        
        data = response.json()
        
        
        logger.debug(f"获取用户信息响应: {data}")
        
        if data.get('code') == 0:
            if data.get('data', {}).get('isLogin', False):
                
                uname = data.get('data', {}).get('uname', '未知用户')
                mid = data.get('data', {}).get('mid', '0')
                logger.info(f"当前登录用户: {uname} (UID: {mid})")
                return data
            else:
                logger.warning("用户未登录")
                return {'code': -101, 'message': '用户未登录'}
        else:
            logger.warning(f"获取用户信息失败: {data.get('message', '未知错误')}")
            return data
            
    except Exception as e:
        logger.error(f"获取用户信息时发生错误: {str(e)}")
        return {'code': -1, 'message': str(e)}


def load_config():
    
    default_config = {
        'deepseek_api_key': '',
        'jfbym_token': '',
        'jfbym_type': '10103',
        'use_cloud_captcha': False,
        'auto_select_category': False,
        'category_id': '6'
    }
    
    try:
        
        if os.path.exists(PROJECT_CONFIG_FILE):
            logger.info(f"使用项目目录配置文件: {PROJECT_CONFIG_FILE}")
            with open(PROJECT_CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
                
                
                for key in default_config:
                    if key not in config:
                        config[key] = default_config[key]
                        
                return config, PROJECT_CONFIG_FILE
        
        
        elif os.path.exists(CONFIG_FILE):
            logger.info(f"使用用户主目录配置文件: {CONFIG_FILE}")
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
                
                
                for key in default_config:
                    if key not in config:
                        config[key] = default_config[key]
                        
                return config, CONFIG_FILE
        else:
            
            logger.info(f"配置文件不存在，将在项目目录创建: {PROJECT_CONFIG_FILE}")
            save_config(default_config, PROJECT_CONFIG_FILE)
            return default_config, PROJECT_CONFIG_FILE
    except Exception as e:
        logger.error(f"加载配置文件出错: {str(e)}")
        return default_config, PROJECT_CONFIG_FILE

def save_config(config, config_path=None):
    
    
    if config_path is None:
        config_path = PROJECT_CONFIG_FILE
        
    try:
        
        dir_path = os.path.dirname(config_path)
        os.makedirs(dir_path, exist_ok=True)
        
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
        logger.info(f"配置已保存到: {config_path}")
    except Exception as e:
        logger.error(f"保存配置文件出错: {str(e)}")

def main():
    try:
        global API_KEY_DEEPSEEK, USE_CLOUD_CAPTCHA, JFBYM_TOKEN, AUTO_SELECT_CATEGORY, AUTO_CATEGORY_ID
        
        print("\n===================================")
        print("B站硬核会员自动答题工具")
        print("版本: 1.0.0")
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"启动时间: {current_time}")
        print("===================================\n")
        
        
        print("如果您喜欢这个工具，可以查看原项目并给作者Star:")
        print("https://github.com/SkyBlue997/BiliRaku")
        print("基于B站API和DeepSeek的硬核会员自动答题工具\n")
        
        
        parser = argparse.ArgumentParser(description='B站硬核会员自动答题工具')
        parser.add_argument('--clean', action='store_true', help='清除之前的登录信息，强制重新登录')
        parser.add_argument('--reset', action='store_true', help='重置所有配置，包括API密钥和配置信息')
        parser.add_argument('--keep', action='store_true', help='保持之前的登录状态，不清除数据')
        parser.add_argument('--config', action='store_true', help='编辑配置文件')
        args = parser.parse_args()
        
        
        has_previous_login = os.path.exists(AUTH_FILE)
        
        
        if not (args.keep or args.clean) and has_previous_login:
            
            previous_auth_info = "未知账户"
            try:
                with open(AUTH_FILE, 'r') as f:
                    auth_data = json.load(f)
                    if 'uid' in auth_data and auth_data['uid']:
                        previous_auth_info = f"UID: {auth_data['uid']}"
                        logger.info(f"找到之前的登录信息: {previous_auth_info}")
            except Exception as e:
                logger.error(f"读取之前的登录信息失败: {str(e)}")
            
            print(f"\n检测到上次登录的账户 ({previous_auth_info})")
            keep_login = input('是否使用上次的账户登录? [1]是 [2]否: ').strip() or '1'
            
            if keep_login == '1':
                logger.info("用户选择使用上次的账户登录")
                args.keep = True  
            else:
                logger.info("用户选择重新登录")
                args.clean = True  
        
        
        if args.clean or (not args.keep and not has_previous_login):
            logger.info("清除之前的登录信息，将重新登录")
            if os.path.exists(AUTH_FILE):
                try:
                    os.remove(AUTH_FILE)
                    logger.info("已清除之前的登录信息")
                except Exception as e:
                    logger.error(f"清除登录信息失败: {str(e)}")
            
            global access_token, csrf
            access_token = None
            csrf = None
        elif args.keep or (not args.clean and has_previous_login):
            logger.info("保留之前的登录信息")
        
        
        if args.reset:
            clear_user_data(force=True)
            
            if os.path.exists(PROJECT_CONFIG_FILE):
                try:
                    os.remove(PROJECT_CONFIG_FILE)
                    logger.info(f"已删除项目目录配置文件: {PROJECT_CONFIG_FILE}")
                except Exception as e:
                    logger.error(f"删除配置文件失败: {str(e)}")
            if os.path.exists(CONFIG_FILE):
                try:
                    os.remove(CONFIG_FILE)
                    logger.info(f"已删除用户目录配置文件: {CONFIG_FILE}")
                except Exception as e:
                    logger.error(f"删除配置文件失败: {str(e)}")
        
        
        config, config_path = load_config()
        
        
        if args.config:
            print(f"\n配置文件位置: {config_path}")
            print("请使用文本编辑器打开并编辑配置文件，然后保存并重新启动程序")
            print("配置项说明:")
            print("  deepseek_api_key: DeepSeek API密钥")
            print("  jfbym_token: 云码API Token")
            print("  jfbym_type: 验证码类型ID (默认B站验证码类型为10103)")
            print("  use_cloud_captcha: 是否使用云码API (true/false)")
            print("  auto_select_category: 是否自动选择分类 (true/false)")
            print("  category_id: 分类ID (6:文史类, 推荐)")
            input("按回车键退出...")
            return
        
        
        API_KEY_DEEPSEEK = config.get('deepseek_api_key', '')
        if not API_KEY_DEEPSEEK:
            logger.info("配置文件中缺少DeepSeek API密钥，请输入")
            API_KEY_DEEPSEEK = input('请输入DeepSeek API密钥: ').strip()
            if API_KEY_DEEPSEEK:
                config['deepseek_api_key'] = API_KEY_DEEPSEEK
                save_config(config, config_path)
            else:
                logger.error("未配置API密钥，程序退出")
                return
        
        
        JFBYM_TOKEN = config.get('jfbym_token', '')
        JFBYM_TYPE = config.get('jfbym_type', '10103')
        USE_CLOUD_CAPTCHA = config.get('use_cloud_captcha', False)
        
        
        if not JFBYM_TOKEN and not USE_CLOUD_CAPTCHA:
            print("是否配置云码API用于自动识别验证码？(不配置将使用浏览器打开验证码)")
            cloud_choice = input("[1]是 [2]否: ").strip()
            if cloud_choice == '1':
                JFBYM_TOKEN = input('请输入云码API token: ').strip()
                
                
                if (JFBYM_TOKEN.startswith('"') and JFBYM_TOKEN.endswith('"')) or \
                (JFBYM_TOKEN.startswith("'") and JFBYM_TOKEN.endswith("'")):
                    JFBYM_TOKEN = JFBYM_TOKEN[1:-1]
                    
                JFBYM_TYPE = input('请输入验证码类型ID (默认B站验证码类型为10103): ').strip() or '10103'
                if JFBYM_TOKEN:
                    
                    config['jfbym_token'] = JFBYM_TOKEN
                    config['jfbym_type'] = JFBYM_TYPE
                    config['use_cloud_captcha'] = True
                    save_config(config, config_path)
                    USE_CLOUD_CAPTCHA = True
                    print("云码API配置已保存")
            else:
                USE_CLOUD_CAPTCHA = False
                config['use_cloud_captcha'] = False
                save_config(config, config_path)
                print("将使用浏览器打开验证码")
        elif JFBYM_TOKEN and USE_CLOUD_CAPTCHA:
            logger.info("已从配置文件加载云码API设置")
        
        
        AUTO_SELECT_CATEGORY = config.get('auto_select_category', False)
        AUTO_CATEGORY_ID = config.get('category_id', '6')
        
        
        if not AUTO_SELECT_CATEGORY and USE_CLOUD_CAPTCHA:
            auto_category = input("是否自动选择分类，无需每次手动选择? [1]是 [2]否: ").strip()
            if auto_category == '1':
                print("请选择默认分类:")
                print("[1] 文史类 (ID: 6) - 推荐")
                AUTO_CATEGORY_ID = '6'
                AUTO_SELECT_CATEGORY = True
                
                config['auto_select_category'] = True
                config['category_id'] = AUTO_CATEGORY_ID
                save_config(config, config_path)
                print(f"已设置自动选择分类ID: {AUTO_CATEGORY_ID}")
            else:
                AUTO_SELECT_CATEGORY = False
                config['auto_select_category'] = False
                save_config(config, config_path)
        elif AUTO_SELECT_CATEGORY:
            logger.info(f"已从配置文件加载分类设置: ID {AUTO_CATEGORY_ID}")
        
        if not auth():
            logger.error("登录失败，程序退出")
            return
        
        quiz = QuizSession()
        quiz.start()
    
    except Exception as e:
        logger.error(f"程序运行出错: {str(e)}")
        import traceback
        logger.error(f"错误详情: {traceback.format_exc()}")
    finally:
        input("按回车键退出程序...")

if __name__ == "__main__":
    main()
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


APP_NAME = 'biliraku'
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, 'logs')
os.makedirs(LOG_DIR, exist_ok=True)


USER_CONFIG_DIR = os.path.join(os.path.expanduser('~'), f'.{APP_NAME}')
os.makedirs(USER_CONFIG_DIR, exist_ok=True)


AUTH_FILE = os.path.join(USER_CONFIG_DIR, 'auth.json')
DEEPSEEK_KEY_FILE = os.path.join(USER_CONFIG_DIR, 'deepseek_key.json')


API_CONFIG = {
    'appkey': '783bbb7264451d82',
    'appsec': '2653583c8873dea268ab9386918b1d65',
    'user_agent': 'Mozilla/5.0 BiliDroid/1.12.0 (bbcallen@gmail.com)',
}


HEADERS = {
    'User-Agent': API_CONFIG['user_agent'],
    'Content-Type': 'application/x-www-form-urlencoded',
    'Accept': 'application/json',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    'x-bili-metadata-legal-region': 'CN',
    'x-bili-aurora-eid': '',
    'x-bili-aurora-zone': '',
}


JFBYM_TOKEN = ""
JFBYM_TYPE = "10101"
USE_CLOUD_CAPTCHA = False
AUTO_SELECT_CATEGORY = False
AUTO_CATEGORY_ID = '6'


access_token = None
csrf = None
API_KEY_DEEPSEEK = None


PROMPT = '''
当前时间：{}
你是一名具备高度准确性与效率的答题专家。在解答选择题时，请依据题干与选项判断最合理的答案，并返回其对应的序号（1, 2, 3, 4）。
示例：
问题：中国第一位皇帝是谁？
选项：['秦始皇', '汉武帝', '唐太宗', '刘邦']
回答：1
如果不能完全确定答案，请选择最接近正确的选项，并返回其序号。不提供额外解释，也不输出 1–4 之外的内容。
---
请回答我的问题：{}
'''


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

def get(url, params):

    try:
        signed_params = appsign(params)
        logger.debug(f'发送GET请求: {url}, 参数: {signed_params}')
        response = session.get(url, params=signed_params, headers=headers)
        response.raise_for_status()
        data = response.json()
        logger.debug(f'请求成功: {data}')
        return data
    except requests.exceptions.HTTPError as e:
        logger.error(f'HTTP错误: {e}\n响应内容: {e.response.text}')
        raise
    except requests.exceptions.RequestException as e:
        logger.error(f'请求失败: {e}')
        raise
    except ValueError as e:
        logger.error(f'解析响应JSON失败: {e}')
        raise

def post(url, params):

    try:
        signed_params = appsign(params)
        logger.debug(f'发送POST请求: {url}, 参数: {signed_params}')
        response = session.post(url, data=signed_params, headers=headers)
        response.raise_for_status()
        data = response.json()
        logger.debug(f'请求成功: {data}')
        return data
    except requests.exceptions.HTTPError as e:
        logger.error(f'HTTP错误: {e}\n响应内容: {e.response.text}')
        raise
    except requests.exceptions.RequestException as e:
        logger.error(f'请求失败: {e}')
        raise
    except ValueError as e:
        logger.error(f'解析响应JSON失败: {e}')
        raise


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
                if all(key in auth_data for key in ['access_token', 'csrf', 'mid', 'cookie']):
                    global access_token, csrf
                    access_token = auth_data['access_token']
                    csrf = auth_data['csrf']
                    headers.update({
                        'x-bili-mid': auth_data['mid'],
                        'cookie': auth_data['cookie']
                    })
                    logger.info('已从缓存加载登录信息')
                    return True
        except Exception as e:
            logger.error(f'读取认证信息失败: {str(e)}')
    return False

def save_auth_data(auth_data):

    try:
        with open(AUTH_FILE, 'w') as f:
            json.dump(auth_data, f, indent=4)
        logger.info('认证信息已保存到缓存')
    except Exception as e:
        logger.error(f'保存认证信息失败: {str(e)}')


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
            response = requests.get(url, headers=headers, timeout=10)
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
        

        data = {
            'softid': '96001',
            'type': JFBYM_TYPE,
            'token': JFBYM_TOKEN
        }
        
        files = {
            'image': ('captcha.jpg', base64_data)
        }
        

        api_url = 'https://v2-api.jsdama.com/upload'
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = requests.post(api_url, data=data, files=files, timeout=15)
                
                if response.status_code == 200:
                    result = response.json()
                    if result.get('code') == 0:
                        captcha_text = result.get('data', {}).get('result')
                        logger.info(f"云码识别成功：{captcha_text}")
                        return captcha_text
                    else:
                        error_msg = result.get('message', '未知错误')
                        logger.warning(f"云码API返回错误: {error_msg}，尝试重试 {attempt+1}/{max_retries}")
                else:
                    logger.warning(f"云码API请求失败，状态码: {response.status_code}，尝试重试 {attempt+1}/{max_retries}")
                

                if attempt < max_retries - 1:
                    time.sleep(random.uniform(1.0, 3.0))
            
            except Exception as e:
                logger.warning(f"云码API请求出错: {str(e)}，尝试重试 {attempt+1}/{max_retries}")
                if attempt < max_retries - 1:
                    time.sleep(1)
        
        logger.error("多次尝试云码API识别验证码失败")
        return None
        
    except Exception as e:
        logger.error(f"处理验证码图片出错: {str(e)}")
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

    res = get('https://api.bilibili.com/x/senior/v1/category', {
        'access_key': access_token,
        'csrf': csrf,
        'disable_rcmd': 0,
        'mobi_app': 'android',
        'platform': 'android',
        'statistics': '{"appId":1,"platform":3,"version":"8.40.0","abtest":""}',
        'web_location': '333.790'
    })
    if res and res.get('code') == 0:
        return res.get('data')
    elif res and res.get('code') == 41099:
        raise Exception('获取分类失败，可能是已经达到答题限制(B站每日限制3次)，请前往B站APP确认是否可以正常答题{}'.format(res))
    else:
        print('获取分类失败，请前往B站APP确认是否可以正常答题{}'.format(res))
        exit()

def captcha_get():

    res = get('https://api.bilibili.com/x/senior/v1/captcha', {
        'access_key': access_token,
        'csrf': csrf,
        'disable_rcmd': 0,
        'mobi_app': 'android',
        'platform': 'android',
        'statistics': '{"appId":1,"platform":3,"version":"8.40.0","abtest":""}',
        'web_location': '333.790'
    })
    if res and res.get('code') == 0:
        return res.get('data')
    else:
        raise Exception('获取验证码失败，请前往B站APP确认是否可以正常答题{}'.format(res))

def captcha_submit(code, captcha_token, ids):

    res = post('https://api.bilibili.com/x/senior/v1/captcha/submit', {
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
    })
    if res and res.get('code') == 0:
        return True
    else:
        raise Exception('提交验证码失败{}'.format(res))

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
    md5hash = hashlib.md5(f"api.bilibili.com/x/internal/oauth2/getHTTPTicket{ts}".encode()).hexdigest()

    return f"{md5hash},{ts}"

def qrcode_get():

    headers.update({'x-bili-ticket': getTicket()})
    res = get('https://passport.bilibili.com/x/passport-login/qrcode/auth', {
        'disable_rcmd': 0,
        'mobi_app': 'android',
        'platform': 'android',
        'statistics': '{"appId":1,"platform":3,"version":"8.40.0","abtest":""}',
        'ts': str(int(time.time())),
        'web_location': '333.790'
    })
    if res and res.get('code') == 0:
        return res.get('data')
    else:
        raise Exception('获取二维码失败{}'.format(res))

def qrcode_poll(auth_code):

    return get('https://passport.bilibili.com/x/passport-login/qrcode/poll', {
        'auth_code': auth_code,
        'disable_rcmd': 0,
        'mobi_app': 'android',
        'platform': 'android',
        'statistics': '{"appId":1,"platform":3,"version":"8.40.0","abtest":""}',
        'web_location': '333.790'
    })

def save_qrcode_image(url):

    try:

        qr_img = qrcode_make(url)
        

        temp_dir = Path(tempfile.gettempdir()) / APP_NAME
        os.makedirs(temp_dir, exist_ok=True)
        

        qr_path = temp_dir / "bili_qrcode.png"
        qr_img.save(qr_path)
        
        logger.info(f"二维码图片已保存到: {qr_path}")
        

        try:
            if platform.system() == "Darwin":
                os.system(f"open {qr_path}")
            elif platform.system() == "Windows":
                os.system(f"start {qr_path}")
            elif platform.system() == "Linux":
                os.system(f"xdg-open {qr_path}")
            logger.info("已自动打开二维码图片")
        except:
            logger.info(f"无法自动打开图片，请手动查看保存的二维码图片: {qr_path}")
            
        return str(qr_path)
    except Exception as e:
        logger.error(f"保存二维码图片失败: {e}")
        return None 


def auth():

    if load_auth_data():
        return True

    try:

        headers.update({'x-bili-ticket': getTicket()})
        qrcode_data = qrcode_get()
        url = qrcode_data.get('url')
        

        qr_image_path = save_qrcode_image(url)
        

        qr = QRCode(
            version=1,
            error_correction=ERROR_CORRECT_L,
            box_size=10,
            border=2
        )


        qr.add_data(url)
        qr.make(fit=True)


        print("\n\n")
        qr.print_ascii()
        print("\n")
        
        logger.info('请使用哔哩哔哩APP扫描二维码登录')
        logger.info('------------------------')
        if qr_image_path:
            logger.info(f"二维码图片已生成在: {qr_image_path}")
        logger.info(f"二维码链接: {url}")
        logger.info('如果二维码显示异常，请复制上面的链接，使用下面任一方法:')
        logger.info('1. 直接在浏览器打开链接，然后用B站APP扫描网页上的二维码')
        logger.info('2. 使用 https://cli.im/ 生成此链接的二维码进行扫码')
        logger.info('------------------------')
        

        auth_code = qrcode_data.get('auth_code')
        retry_count = 0
        max_retries = 60

        while retry_count < max_retries:
            try:
                poll_data = qrcode_poll(auth_code)
                if poll_data.get('code') == 0:
                    data = poll_data.get('data')
                    auth_data = {
                        'access_token': data.get('access_token'),
                        'mid': str(data.get('mid')),
                    }

                    cookies = data.get('cookie_info').get('cookies')
                    for cookie in cookies:
                        if cookie.get('name') == 'bili_jct':
                            auth_data.update({'csrf': cookie.get('value')})
                            break
                    cookie_str = ';'.join([f"{cookie.get('name')}={cookie.get('value')}" for cookie in cookies])
                    auth_data.update({'cookie': cookie_str})

                    global access_token, csrf
                    access_token = auth_data['access_token']
                    csrf = auth_data['csrf']
                    headers.update({
                        'x-bili-mid': auth_data['mid'],
                        'cookie': auth_data['cookie']
                    })


                    save_auth_data(auth_data)
                    logger.info('登录成功')
                    return True

            except Exception as e:
                logger.error(f'轮询二维码状态失败: {str(e)}')

            time.sleep(1)
            retry_count += 1

        logger.error('二维码登录超时')
        return False

    except Exception as e:
        logger.error(f'认证过程发生错误: {str(e)}')
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
                return False
            
            ids = '6'
            logger.info(f"已自动选择: 文史类 (ID: {ids})")
            
            logger.info("获取验证码...")
            captcha_res = captcha_get()
            captcha_url = captcha_res.get('url')
            logger.info(f"验证码链接: {captcha_url}")
            
            if not captcha_res:
                return False
            
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
                    if captcha_submit(code=captcha, captcha_token=captcha_res.get('token'), ids=ids):
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
                    if retry_count >= max_retries:
                        logger.error(f"提交验证码失败: {str(e)}")
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


def main():
    try:
        global API_KEY_DEEPSEEK, USE_CLOUD_CAPTCHA, JFBYM_TOKEN, AUTO_SELECT_CATEGORY, AUTO_CATEGORY_ID
        
        API_KEY_DEEPSEEK = load_api_key()
        if not API_KEY_DEEPSEEK:
            logger.info("首次使用需配置DeepSeek API密钥")
            API_KEY_DEEPSEEK = input('请输入DeepSeek API密钥: ').strip()
            if API_KEY_DEEPSEEK:
                save_api_key(API_KEY_DEEPSEEK)
            else:
                logger.error("未配置API密钥，程序退出")
                return
        
        cloud_config_path = os.path.join(USER_CONFIG_DIR, 'jfbym_key.json')
        if os.path.exists(cloud_config_path):
            try:
                with open(cloud_config_path, 'r') as f:
                    cloud_data = json.load(f)
                    JFBYM_TOKEN = cloud_data.get('token', '')
                    JFBYM_TYPE = cloud_data.get('type', '10101')
                    if JFBYM_TOKEN:
                        USE_CLOUD_CAPTCHA = True
                        logger.info("已加载云码API配置")
            except Exception as e:
                logger.error(f"读取云码配置失败: {str(e)}")
                
        category_config_path = os.path.join(USER_CONFIG_DIR, 'category_config.json')
        if os.path.exists(category_config_path):
            try:
                with open(category_config_path, 'r') as f:
                    category_data = json.load(f)
                    AUTO_SELECT_CATEGORY = category_data.get('auto_select', False)
                    if AUTO_SELECT_CATEGORY:
                        AUTO_CATEGORY_ID = category_data.get('category_id', '6')
                        logger.info(f"已加载自动分类配置: ID {AUTO_CATEGORY_ID}")
            except Exception as e:
                logger.error(f"读取分类配置失败: {str(e)}")
        
        if not USE_CLOUD_CAPTCHA:
            print("是否配置云码API用于自动识别验证码？(不配置将使用浏览器打开验证码)")
            cloud_choice = input("[1]是 [2]否: ").strip()
            if cloud_choice == '1':
                JFBYM_TOKEN = input('请输入云码API token(需用引号包裹): ').strip()
                if (JFBYM_TOKEN.startswith('"') and JFBYM_TOKEN.endswith('"')) or \
                (JFBYM_TOKEN.startswith("'") and JFBYM_TOKEN.endswith("'")):
                    JFBYM_TOKEN = JFBYM_TOKEN[1:-1]
                    
                JFBYM_TYPE = input('请输入验证码类型ID (默认B站验证码类型为10101): ').strip() or '10101'
                if JFBYM_TOKEN:
                    try:
                        os.makedirs(USER_CONFIG_DIR, exist_ok=True)
                        with open(cloud_config_path, 'w') as f:
                            json.dump({'token': JFBYM_TOKEN, 'type': JFBYM_TYPE}, f)
                        print("云码API配置已保存")
                        USE_CLOUD_CAPTCHA = True
                    except Exception as e:
                        logger.error(f"保存云码配置失败: {str(e)}")
                    
                    auto_category = input("是否自动选择分类，无需每次手动选择? [1]是 [2]否: ").strip()
                    if auto_category == '1':
                        print("请选择默认分类:")
                        print("[1] 文史类 (ID: 6) - 推荐")
                        AUTO_CATEGORY_ID = '6'
                        AUTO_SELECT_CATEGORY = True
                        print(f"已设置自动选择分类ID: {AUTO_CATEGORY_ID}")
                        try:
                            with open(category_config_path, 'w') as f:
                                json.dump({'auto_select': True, 'category_id': AUTO_CATEGORY_ID}, f)
                        except Exception as e:
                            logger.error(f"保存分类配置失败: {str(e)}")
            else:
                USE_CLOUD_CAPTCHA = False
                print("将使用浏览器打开验证码")
        
        if not auth():
            logger.error("登录失败，程序退出")
            return
        
        quiz = QuizSession()
        quiz.start()
    
    except Exception as e:
        logger.error(f"程序运行出错: {str(e)}")
    finally:
        input("按回车键退出程序...")

if __name__ == "__main__":
    main() 
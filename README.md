# BiliRaku - B站硬核会员自动答题工具

基于B站API和DeepSeek的硬核会员自动答题工具。

## 🚀 使用说明

### 环境要求
- Python 3.9及以上版本
- 必要的Python库：requests, qrcode, pillow等

### 安装步骤

1. 克隆本仓库到本地
```bash
git clone https://github.com/SkyBlue997/BiliRaku
cd biliraku
```

2. 安装依赖包
```bash
pip install -r requirements.txt
```

3. 运行程序
```bash
python biliraku.py
```

### 首次使用配置

1. **DeepSeek API配置**
   - 首次使用时，需要输入DeepSeek API密钥
   - 可在[DeepSeek官网](https://platform.deepseek.com/api_keys)申请API密钥
   - API密钥将安全保存在用户目录下，不会上传到网络

2. **云码API配置（可选）**
   - 如需使用自动识别验证码功能，可配置[云码API](https://www.jfbym.com)
   - 提供云码API Token后，系统将自动识别B站验证码
   - 不配置则使用浏览器打开验证码，手动输入

3. **分类选择**
   - 程序选择文史类(ID: 6)进行答题
   - 文史类题目通常通过率更高
   - 答题入口可在[B站硬核会员答题页面](https://www.bilibili.com/v/hardgame)找到

## ⚙️ 配置说明

### config.json 配置文件
程序支持以下配置项：
```json
{
  "deepseek_api_key": "",        // DeepSeek AI API密钥
  "jfbym_token": "",            // 云码验证码识别API令牌
  "jfbym_type": "10103",        // B站验证码类型ID
  "use_cloud_captcha": true,    // 是否使用云码API识别验证码
  "auto_select_category": true, // 是否自动选择答题分类
  "category_id": "6"           // 默认答题分类ID (6=文史类)
}
```

### 参数说明
- `deepseek_api_key`: 必填，用于AI答题的DeepSeek API密钥
- `jfbym_token`: 可选，用于自动识别验证码的云码API Token
- `use_cloud_captcha`: 是否启用云码API自动识别验证码
- `auto_select_category`: 是否自动选择答题分类
- `category_id`: 答题分类ID，推荐使用6(文史类)

### 配置文件位置
程序按以下顺序查找配置文件：
1. 项目目录下的 config.json
2. 用户主目录下的 .biliraku/config.json

### 命令行参数
程序支持以下命令行参数：
```bash
--clean    # 清除之前的登录信息，强制重新登录
--reset    # 重置所有配置，包括API密钥和配置信息
--keep     # 保持之前的登录状态，不清除数据
--config   # 编辑配置文件
```

## 📚 使用流程

1. **登录B站账号**
   - 系统生成二维码（终端ASCII展示+图片形式）
   - 使用B站APP扫描二维码完成登录
   - 登录信息将缓存7天，期间无需重复登录

2. **验证码处理**
   - 自动获取验证码
   - 若配置了云码API，自动识别验证码
   - 否则在浏览器中打开验证码图片，手动输入

3. **自动答题**
   - 系统自动获取题目并调用DeepSeek AI回答
   - 显示题目、选项和AI给出的答案
   - 自动提交答案并展示结果
   - 答题完成后显示总得分和通过状态

## ⚙️ 高级功能

### 验证码自动识别
程序支持使用云码API自动识别B站验证码，提高答题流程的自动化程度：
```
是否配置云码API用于自动识别验证码？(不配置将使用浏览器打开验证码)
[1]是 [2]否: 1
请输入云码API token(需用引号包裹): "your_token_here"
```

### 自动选择分类
为简化操作，程序已自动配置为使用文史类作答：
```
已自动选择: 文史类 (ID: 6)
```

### 智能识别答案
程序使用DeepSeek V3模型自动分析题目并给出答案：
```
正在作答第 2 题
题目: 下列哪部作品是乔治·奥威尔创作的？
选项1: 《百年孤独》
选项2: 《动物农场》
选项3: 《红与黑》
选项4: 《包法利夫人》
AI给出的答案:2
正在提交答案: 《动物农场》 (hash: 58c9e530cd02c8ac)
提交结果: ✓ 正确
```

## 🔍 常见问题

1. **二维码显示异常**
   - 在Windows Terminal中运行可获得更好的二维码显示效果
   - 使用程序自动保存的二维码图片进行扫描
   - 复制控制台输出的链接，使用在线二维码生成工具生成

2. **验证码识别失败**
   - 云码API可能受额度限制，考虑手动输入
   - 尝试重新运行程序，获取新的验证码

3. **答题失败**
   - DeepSeek API出错时，系统会随机选择一个答案继续

4. **连接错误**
   - 检查网络连接是否正常
   - 确认DeepSeek API密钥是否有效

5. **配置文件问题**
   - 首次运行会在项目目录创建默认配置文件
   - 可使用 --config 参数打开并编辑配置
   - 建议保管好API密钥，避免泄露

## 🛡️ 免责声明

- 本工具仅供学习研究使用，请勿用于任何商业用途
- 使用过程中遵守B站相关规则和条款
- 本工具不会上传或存储您的个人敏感信息
- 使用本工具产生的任何风险由使用者自行承担


## 📄 许可证

本项目采用MIT许可证 - 详情请参阅LICENSE文件
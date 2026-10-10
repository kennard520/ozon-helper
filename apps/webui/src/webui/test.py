import base64
import os

from openai import OpenAI

# 1. 配置客户端
client = OpenAI(
    api_key="YOUR_API_KEY",  # 替换成你的真实 API Key
    base_url="https://api.deepseek.com"  # DeepSeek 的 API 地址
)


# 2. 辅助函数：读取图片并转成 Base64
def encode_image(image_path):
    """读取本地图片，返回其Base64编码字符串"""
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")


# 3. 指定图片路径并编码
image_path = "你的图片路径.jpg"  # 改成你的图片路径
base64_image = encode_image(image_path)

# 4. 调用 API 进行分析
try:
    response = client.chat.completions.create(
        model="deepseek-v4-flash",  # 或 "deepseek-v4-pro"
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{base64_image}"
                        }
                    },
                    {
                        "type": "text",
                        "text": "请描述这张图片的内容，并用中文回复。"  # 你的问题
                    }
                ]
            }
        ],
        max_tokens=1000
    )

    # 5. 打印模型的回答
    print("模型回答：", response.choices[0].message.content)

except Exception as e:
    print(f"出错了: {e}")

# -*- coding: utf-8 -*-
from flask import Flask, render_template, request, jsonify, send_file
from openai import OpenAI
import pandas as pd
import requests
import tempfile
import os
import random

app = Flask(__name__)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
GNEWS_API_KEY = "6e7d2499dd21d867dad271d86b0cab92" # 請替換成您的 API 金鑰
CSV_PATH = "math_lessons_cleaned.csv"# 請確保此路徑正確，或使用相對路徑並將檔案放在同目錄

try:
    df_math = pd.read_csv(CSV_PATH)
except FileNotFoundError:
    print(f"錯誤：找不到 CSV 檔案於 {CSV_PATH}。請檢查路徑或檔案是否存在。")
    df_math = pd.DataFrame()

audio_tempfile_path = None

@app.route('/')
def index():
    return render_template("index.html") # 確保這個 HTML 檔案名稱與您前端使用的檔案一致

@app.route('/get-news')
def get_news():
    category = request.args.get('category', 'general')
    url = "https://gnews.io/api/v4/top-headlines"
    params = {
        "token": GNEWS_API_KEY,
        "lang": "zh",
        "topic": category,
        "max": 3
    }
    try:
        res = requests.get(url, params=params)
        res.raise_for_status()
        data = res.json()
        news_list = []
        for item in data.get("articles", []):
            title = item.get("title", "")
            content = item.get("description", "")
            summary = simplify_news(title, content)
            news_list.append({"title": title, "summary": summary})
        return jsonify(news_list)
    except requests.exceptions.RequestException as e:
        print(f"GNews API 請求錯誤: {e}")
        return jsonify({"error": "無法獲取新聞"}), 500
    except Exception as e:
        print(f"處理新聞時發生未知錯誤: {e}")
        return jsonify({"error": "處理新聞時發生錯誤"}), 500

def simplify_news(title, content):
    prompt = f"請用台灣小學生能理解的方式，摘要這則新聞：標題：{title} 內容：{content}"
    try:
        completion = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "你是一位會說中文的新聞摘要助手，專為小學生解說。"},
                {"role": "user", "content": prompt}
            ]
        )
        return completion.choices[0].message.content.strip()
    except Exception as e:
        print(f"OpenAI API 呼叫失敗 (simplify_news): {e}")
        return "無法生成新聞摘要。"

@app.route('/play-news-tts', methods=['POST'])
def play_news_tts():
    global audio_tempfile_path
    text = request.json.get("text", "")
    if not text:
        return jsonify({"error": "沒有提供文字來生成語音"}), 400
    try:
        response = client.audio.speech.create(model="tts-1", voice="shimmer", input=text)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as fp:
            fp.write(response.content)
            audio_tempfile_path = fp.name
        return jsonify({"audio_url": "/news-audio"})
    except Exception as e:
        print(f"OpenAI TTS API 呼叫失敗: {e}")
        if audio_tempfile_path and os.path.exists(audio_tempfile_path):
            try:
                os.remove(audio_tempfile_path)
            except OSError as oe:
                print(f"刪除臨時音訊檔案失敗: {oe}")
            audio_tempfile_path = None
        return jsonify({"error": "無法生成語音"}), 500

@app.route('/news-audio')
def news_audio():
    global audio_tempfile_path
    try:
        if audio_tempfile_path and os.path.exists(audio_tempfile_path):
            return send_file(audio_tempfile_path, mimetype="audio/mpeg", as_attachment=False)
        else:
            return "音訊檔案不存在或已過期", 404
    finally:
        if audio_tempfile_path and os.path.exists(audio_tempfile_path):
             try:
                 pass
             except OSError as e:
                 print(f"刪除臨時音訊檔案失敗: {e}")

@app.route('/get-math-units')
def get_math_units():
    if df_math.empty:
        return jsonify([])
    units = df_math['單元小節'].dropna().unique().tolist()
    return jsonify(units)

@app.route("/generate-math-question")
def generate_math_question():
    if df_math.empty:
        return jsonify({"question": "(數學資料未載入)", "answer": "", "explanation": ""})

    unit = request.args.get("unit", "")
    if not unit:
        available_units = df_math['單元小節'].dropna().unique().tolist()
        if not available_units:
            return jsonify({"question": "(沒有可用的數學單元)", "answer": "", "explanation": ""})
        unit = random.choice(available_units)
        print(f"未指定單元，隨機選擇: {unit}")

    sub_df_all_rows = df_math[df_math['單元小節'] == unit]

    if sub_df_all_rows.empty:
        return jsonify({"question": f"(找不到此單元: {unit})", "answer": "", "explanation": ""})

    # 由於每個單元目前只有一行，sample(n=1) 實際上是選取那唯一的一行
    # 如果未來 CSV 中一個單元有多行不同素材，這裡的 sample()纔會真正隨機
    sub_df = sub_df_all_rows.sample(n=1)
    selected_row = sub_df.iloc[0]

    title = selected_row["單元名稱"] if "單元名稱" in selected_row and pd.notna(selected_row["單元名稱"]) else "未知單元"
    story = selected_row["小故事"] if "小故事" in selected_row and pd.notna(selected_row["小故事"]) else "沒有小故事"
    knowledge = selected_row["知識點"] if "知識點" in selected_row and pd.notna(selected_row["知識點"]) else "沒有知識點"

    examples = []
    for i in range(1, 6):
        q_col = f"練習{i}"
        a_col = f"答案{i}"
        if q_col in selected_row.index and a_col in selected_row.index:
            q_val = selected_row[q_col]
            a_val = selected_row[a_col]
            if pd.notna(q_val) and pd.notna(a_val):
                q = str(q_val).strip()
                a = str(a_val).strip()
                if q and a and q.lower() != "nan":
                    examples.append(f"Q{i}: {q} A: {a}")

    if not examples:
        examples.append("Q1: 小明有3個籃子，每個籃子有4顆蘋果，總共有幾顆？ A: 12")

    # MODIFICATION START: Adjust example_text based on the unit or for randomness
    # 複製一份範例列表，以避免修改原始從 DataFrame 中提取的列表
    current_examples = list(examples)
    random.shuffle(current_examples) # 打亂範例順序

    # 您可以選擇以下一種策略來構成 example_text，或者根據單元來決定
    # 策略 1: 使用全部打亂順序後的範例 (這是您檔案中已有的邏輯，但確保在 current_examples 上操作)
    example_text = "\\n".join(current_examples)

    # 策略 2: (可選實驗) 只選取部分打亂順序後的範例，例如前2或3個
    # if unit == "2-1": # 可以針對特定單元或所有單元
    #     example_text = "\\n".join(current_examples[:2]) # 取前2個
    # elif unit == "some_other_unit":
    #     example_text = "\\n".join(current_examples[:3]) # 取前3個
    # else:
    #     example_text = "\\n".join(current_examples) # 其他單元使用全部打亂的範例

    # 策略 3: (可選實驗) 對於某些單元，嘗試完全不提供範例
    # if unit == "2-1":
    #     example_text = "（請根據主題、小故事和知識點自由發揮出題，不需要嚴格參考範例。）"
    # else:
    #     example_text = "\\n".join(current_examples)
    # MODIFICATION END

    prompt_text = f"""你是一位國小數學老師。請根據以下資料, 出一題新的小學數學練習題, 並以 JSON 格式輸出題目
【主題】{title}
【小故事】{story}
【知識點】{knowledge}
【題目範例】
{example_text}

請仿照風格，以 JSON 格式輸出：
{{
  "question": "...",
  "answer": "...",
  "explanation": "..."
}}
"""
    print("="*50)
    print(f"請求單元: {unit}")
    print(f"傳送給 GPT 的 Prompt:\n{prompt_text}")
    print("="*50)

    try:
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "你是一位會寫國小數學題目的助教，輸出格式一定要是 JSON"},
                {"role": "user", "content": prompt_text}
            ],
            temperature=0.8 # 您提供的檔案中已包含此設定 [cite: 1]
        )
        raw_reply = response.choices[0].message.content.strip()
        print("GPT 回傳內容 (generate_math_question)：", raw_reply)

        import json
        import re
        try:
            cleaned_reply = re.sub(r'^```json\s*|\s*```$', '', raw_reply, flags=re.MULTILINE | re.DOTALL).strip()
            result = json.loads(cleaned_reply)
        except json.JSONDecodeError:
            print("JSON 直接解析失敗，嘗試使用正規表達式救援。")
            q_match = re.search(r'"question"\s*:\s*"((?:\\"|[^"])*)"', cleaned_reply, re.IGNORECASE)
            a_match = re.search(r'"answer"\s*:\s*"((?:\\"|[^"])*)"', cleaned_reply, re.IGNORECASE)
            e_match = re.search(r'"explanation"\s*:\s*"((?:\\"|[^"])*)"', cleaned_reply, re.IGNORECASE)
            result = {
                "question": q_match.group(1).strip().replace('\\"', '"') if q_match else "(GPT題目解析失敗)",
                "answer": a_match.group(1).strip().replace('\\"', '"') if a_match else "(GPT答案解析失敗)",
                "explanation": e_match.group(1).strip().replace('\\"', '"') if e_match else "(GPT解說解析失敗)"
            }
        return jsonify(result)

    except Exception as e:
        print(f"OpenAI API 或 JSON 處理錯誤 (generate_math_question): {e}")
        return jsonify({
            "question": "(GPT 回應失敗或資料處理錯誤)",
            "answer": "",
            "explanation": f"錯誤：{str(e)}"
        }), 500

@app.route("/check-answer", methods=["POST"])
def check_answer():
    data = request.get_json()
    question = data.get("question", "")
    user_answer = data.get("answer", "")

    if not question or not user_answer:
        return jsonify({"explanation": "請提供題目和您的答案。"}), 400

    prompt = f"""你是一位小學數學老師, 請幫學生檢查答案是否正確, 並提供簡單解說.
題目如下:
{question}
學生的答案是: "{user_answer}"

請判斷這個答案是否正確, 並給出簡單的解說."""

    try:
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "你是一位親切的小學數學老師，會判斷學生答案是否正確，並用小學生聽得懂的方式回應。"},
                {"role": "user", "content": prompt}
            ]
        )
        explanation = response.choices[0].message.content.strip()
        return jsonify({ "explanation": explanation })
    except Exception as e:
        print(f"OpenAI API 呼叫失敗 (check_answer): {e}")
        return jsonify({"explanation": "無法檢查答案，請稍後再試。"}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
import os
import re
import sys
import json
import requests

# ======================
#  读取环境变量
# ======================
GLADOS_COOKIES = os.getenv("GLADOS", "").strip()   # 多账号用换行分隔
SENDKEY = os.getenv("SENDKEY", "").strip()         # Server酱 SendKey

UA = "Mozilla/4.0 (compatible; MSIE 7.0; Windows NT 6.0)"

CHECKIN_URL = "https://railgun.info/api/user/checkin"
STATUS_URL  = "https://railgun.info/api/user/status"
REFERER     = "https://railgun.info/console/checkin"

# 视为“签到流程正常结束”的关键词（包括重复签到）
SUCCESS_KEYWORDS = [
    "Checkin! Got",                             # 成功获得点数
    "Checkin Repeats! Please Try Tomorrow",     # 旧版重复签到提示
    "Today's observation logged. Return tomorrow for more points.", # 新版重复签到提示
]

# 专门标记“重复签到”的关键词（用于区分成功与重复）
REPEAT_KEYWORDS = [
    "Checkin Repeats",
    "Today's observation logged",
]


def sc_send(sendkey: str, title: str, desp: str = ""):
    """通过 Server酱 发送通知"""
    if not sendkey:
        return None

    try:
        if sendkey.startswith("sctp"):
            # 新格式：sctp{num}t{key}
            match = re.match(r"sctp(\d+)t", sendkey)
            if not match:
                raise ValueError("Invalid sendkey format for sctp")
            num = match.group(1)
            url = f"https://{num}.push.ft07.com/send/{sendkey}.send"
        else:
            url = f"https://sctapi.ftqq.com/{sendkey}.send"

        payload = {"title": title, "desp": desp}
        headers = {"Content-Type": "application/json;charset=utf-8"}
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") == 0 or data.get("errno") == 0:
            print(f"Server酱推送成功: {title}")
        else:
            print(f"Server酱推送失败: {data}")
        return data
    except Exception as e:
        print(f"Server酱推送异常: {e}")
        return None


def glados_checkin():
    if not GLADOS_COOKIES:
        print("未设置 GLADOS 环境变量，跳过签到")
        if SENDKEY:
            sc_send(SENDKEY, "GLaDOS 签到", "未检测到 COOKIES")
        return

    cookies_list = [c.strip() for c in GLADOS_COOKIES.split("&") if c.strip()]

    results = []           # 收集每个账号的结果
    has_real_error = False # 标记是否有真正失败的账号

    for idx, cookie in enumerate(cookies_list, 1):
        print(f"\n===== 账号 {idx} =====")

        headers = {
            "cookie": cookie,
            "referer": REFERER,
            "user-agent": UA,
            "content-type": "application/json",
        }

        # 默认结果（最坏情况）
        account_result = {
            "idx": idx,
            "email": "未知",
            "status": "签到失败",
            "points": 0,
            "balance": 0,
            "left_days": "未知",
        }

        try:
            # 1. 签到
            checkin_resp = requests.post(
                CHECKIN_URL,
                headers=headers,
                json={"token": "railgun.info"},
                timeout=15
            )
            checkin_resp.raise_for_status()
            action = checkin_resp.json()

            message = action.get("message", "").strip()
            code = action.get("code")
            points = action.get("points", 0)   # 本次获得点数（成功时才有）
            # 从返回的 list 中获取总积分（可能没有）
            balance = 0
            if "list" in action and action["list"]:
                balance = int(float(action["list"][0].get("balance", 0)))
            else:
                # 尝试其他字段
                balance = int(float(action.get("balance", 0)))

            # 打印原始返回，便于调试
            print(f"签到返回 code={code} | message={message}")

            # 判断签到状态
            is_repeat = any(k in message for k in REPEAT_KEYWORDS) if message else False
            is_success = code == 0 or any(k in message for k in SUCCESS_KEYWORDS)

            if not is_success:
                raise ValueError(f"签到失败（非重复）: code={code} message={message}")

            # 填充结果
            account_result["points"] = int(float(points)) if points else 0
            account_result["balance"] = balance

            if is_repeat or (code and code != 0):  # code 可能为 1 表示重复
                account_result["status"] = "已签到"
            else:
                account_result["status"] = "签到成功"

            # 2. 获取剩余天数与邮箱
            try:
                status_resp = requests.get(STATUS_URL, headers=headers, timeout=10)
                status_resp.raise_for_status()
                status_data = status_resp.json()
                data = status_data.get("data", {})
                email = data.get("email", "未知")
                left_days = data.get("leftDays", "未知")
                if isinstance(left_days, (int, float)):
                    left_days = f"{float(left_days):.2f} 天"
                else:
                    left_days = f"{left_days} 天"

                account_result["email"] = email
                account_result["left_days"] = left_days

                print(f"签到结果: {message}")
                print(f"剩余天数: {left_days} | 邮箱: {email}")
            except Exception as e:
                print(f"获取状态失败，但签到已算正常: {e}")
                # 保持默认值

        except requests.exceptions.RequestException as e:
            print(f"网络请求失败: {e}")
            has_real_error = True
        except ValueError as e:
            print(f"签到异常: {e}")
            has_real_error = True
        except Exception as e:
            print(f"其他错误: {type(e).__name__}: {e}")
            has_real_error = True

        results.append(account_result)

    # 构造推送内容
    success_count = sum(1 for r in results if r["status"] == "签到成功")
    repeat_count = sum(1 for r in results if r["status"] == "已签到")
    fail_count = sum(1 for r in results if r["status"] == "签到失败")

    title = f"GLaDOS 签到 | 成功{success_count} 重复{repeat_count} 失败{fail_count}"
    lines = [
        f"#{r['idx']} {r['email']} | {r['status']} | 获得:{r['points']} | 总积分:{r['balance']} | 剩余:{r['left_days']} \n"
        for r in results
    ]
    content = "\n".join(lines)

    # 控制台也输出结果
    print(f"\n{title}")
    print(content)

    # 发送推送（如果配置了 SENDKEY）
    if SENDKEY:
        sc_send(SENDKEY, title, content)
    else:
        print("未设置 SENDKEY，跳过推送")

    # 最终退出码：只要有一个真正失败，就让 Actions 失败（发邮件）
    if has_real_error:
        print("\n存在至少一个账号签到真正失败 → 设置退出码 1 以触发通知")
        sys.exit(1)
    else:
        print("\n签到成功！所有账号签到流程正常结束")
        sys.exit(0)


def main():
    glados_checkin()


if __name__ == "__main__":
    main()

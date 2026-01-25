import os
import json
import time
import random
import requests
import re
from pypushdeer import PushDeer


CHECKIN_URL = "https://glados.cloud/api/user/checkin"
STATUS_URL = "https://glados.cloud/api/user/status"

HEADERS_BASE = {
    "origin": "https://glados.cloud",
    "referer": "https://glados.cloud/console/checkin",
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "content-type": "application/json;charset=UTF-8",
}

PAYLOAD = {"token": "glados.cloud"}
TIMEOUT = 10


def sc_send(sendkey: str, title: str, desp: str = "", options=None, timeout=10):
  if not sendkey:
    return None
  if options is None:
    options = {}

  # sctp{num}t... -> https://{num}.push.ft07.com/send/{sendkey}.send
  if sendkey.startswith("sctp"):
    match = re.match(r"sctp(\d+)t", sendkey)
    if not match:
      raise ValueError("Invalid sendkey format for sctp")
    num = match.group(1)
    url = f"https://{num}.push.ft07.com/send/{sendkey}.send"
  else:
    # 旧版 -> https://sctapi.ftqq.com/{sendkey}.send
    url = f"https://sctapi.ftqq.com/{sendkey}.send"

  payload = {"title": title, "desp": desp, **options}
  headers = {"Content-Type": "application/json;charset=utf-8"}

  resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
  # Server酱一般返回 JSON；这里做个容错
  try:
    return resp.json()
  except Exception:
    return {"ok": False, "status_code": resp.status_code, "text": resp.text}


# def sc_send(sendkey: str, title: str, desp: str = "", options=None, timeout=10):
#   return 0

def safe_json(resp):
    try:
        return resp.json()
    except Exception:
        return {}


def main():
    sckey = os.getenv("SENDKEY", "")
    cookies_env = os.getenv("COOKIES", "")
    cookies = [c.strip() for c in cookies_env.split("&") if c.strip()]

    if not cookies:
        sc_send(sckey, "GLaDOS 签到", "未检测到 COOKIES")
        return

    session = requests.Session()
    ok = fail = repeat = 0
    lines = []
    status = ''
    email = "unknown"
    points = "-"
    days = "-"
    title = "-"

    for idx, cookie in enumerate(cookies, 1):
        headers = dict(HEADERS_BASE)
        headers["cookie"] = cookie

        try:
            r = session.post(
                CHECKIN_URL,
                headers=headers,
                data=json.dumps(PAYLOAD),
                timeout=TIMEOUT,
            )

            j = safe_json(r)
            msg = j.get("message", "")
            msg_lower = msg.lower()

            # 状态接口（允许失败）
            s = session.get(STATUS_URL, headers=headers, timeout=TIMEOUT)
            sj = safe_json(s).get("data") or {}
            email = sj.get("email", email)
            if sj.get("leftDays") is not None:
                days = f"{int(float(sj['leftDays']))} 天"
            
            if "got" in msg_lower:
                ok += 1
                points = j.get("points", "-")
                status = "签到成功"
                title = f"{email} | P:{points} | D:{days}"
            elif "repeat" in msg_lower or "already" in msg_lower:
                repeat += 1
                status = "已签到"
                title = f"{email} | {status} | D:{days}"
            else:
                fail += 1
                status = "签到失败"
                title = f"{email} | {status} 尽快检查！"

        except Exception:
            fail += 1
            status = "异常"
            title = f"{email} | {status} 尽快检查！"

        lines.append(f"{idx}. {email} | {status} | 获得点数:{points} | 剩余:{days}")
        time.sleep(random.uniform(1, 2))

    
    content = "\n".join(lines)

    # print(title)
    # print(content)
    sc_send(sckey, title, content)


if __name__ == "__main__":
    main()

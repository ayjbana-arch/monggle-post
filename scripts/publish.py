#!/usr/bin/env python3
"""posts/YYYY-MM-DD/ (1.jpg 2.jpg 3.jpg caption.txt) 를 인스타 캐러셀로 게시한다.

CANCEL 파일이 있으면 게시하지 않고, POSTED 파일이 있으면 다시 올리지 않는다.
"""
import datetime
import json
import os
import pathlib
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API = os.environ.get("IG_API_BASE", "https://graph.facebook.com/v23.0")
TOKEN = os.environ["IG_ACCESS_TOKEN"]
REPO = os.environ["GITHUB_REPOSITORY"]
SHA = os.environ["GITHUB_SHA"]
RAW = os.environ.get("RAW_BASE", "https://raw.githubusercontent.com")
IG_USER_ID = os.environ["IG_USER_ID"]
EXPECTED_USERNAME = os.environ.get("EXPECTED_USERNAME", "monggle_recipe")
KST = datetime.timezone(datetime.timedelta(hours=9))
IMAGES = ("1.jpg", "2.jpg", "3.jpg")


def call(method, path, params=None):
    params = dict(params or {})
    data = None
    url = f"{API}/{path}"
    headers = {"Authorization": f"Bearer {TOKEN}"}
    if method == "POST":
        data = urllib.parse.urlencode(params).encode()
    elif params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        # 응답 본문에는 토큰이 없고 원인 메시지만 있다.
        sys.exit(f"인스타 API 오류 {e.code} ({path}): {e.read().decode(errors='replace')}")


def wait_ready(container_id):
    for _ in range(30):
        status = call("GET", container_id, {"fields": "status_code"}).get("status_code")
        if status == "FINISHED":
            return
        if status in ("ERROR", "EXPIRED"):
            sys.exit(f"컨테이너 {container_id} 실패: {status}")
        time.sleep(5)
    sys.exit(f"컨테이너 {container_id} 처리 시간 초과")


def main():
    date = (sys.argv[1] if len(sys.argv) > 1 and sys.argv[1]
            else datetime.datetime.now(KST).strftime("%Y-%m-%d"))
    if date == "check":
        # 게시 없이 토큰과 계정 접근만 확인한다.
        me = call("GET", IG_USER_ID, {"fields": "username"})
        print(f"확인 성공: {me.get('username')} {datetime.datetime.now(KST):%Y-%m-%d %H:%M}")
        return
    folder = pathlib.Path("posts") / date
    if not folder.is_dir():
        print(f"{date}: 게시물 폴더 없음, 종료")
        return
    if (folder / "CANCEL").exists():
        print(f"{date}: CANCEL 있음, 게시 안 함")
        return
    if (folder / "POSTED").exists():
        print(f"{date}: 이미 게시됨")
        return

    missing = [n for n in (*IMAGES, "caption.txt") if not (folder / n).exists()]
    if missing:
        sys.exit(f"{date}: 파일 없음 {missing}")
    caption = (folder / "caption.txt").read_text(encoding="utf-8").strip()
    if not caption or len(caption) > 2200:
        sys.exit(f"{date}: 캡션 길이 이상 ({len(caption)}자)")

    ig_id = IG_USER_ID
    me = call("GET", ig_id, {"fields": "username"})
    if me.get("username") != EXPECTED_USERNAME:
        sys.exit(f"다른 계정입니다: {me.get('username')}")

    # 마커를 못 남긴 채 재실행돼도 같은 글이 두 번 올라가지 않게 최근 게시물과 비교한다.
    recent = call("GET", f"{ig_id}/media", {"fields": "caption,permalink", "limit": 5})
    for m in recent.get("data", []):
        if (m.get("caption") or "").strip() == caption:
            print(f"{date}: 같은 캡션이 이미 게시됨 {m.get('permalink')}")
            (folder / "POSTED").write_text(m.get("permalink") or "", encoding="utf-8")
            return

    children = []
    for name in IMAGES:
        url = f"{RAW}/{REPO}/{SHA}/posts/{date}/{name}"
        c = call("POST", f"{ig_id}/media", {"image_url": url, "is_carousel_item": "true"})
        wait_ready(c["id"])
        children.append(c["id"])

    carousel = call("POST", f"{ig_id}/media", {
        "media_type": "CAROUSEL",
        "children": ",".join(children),
        "caption": caption,
    })
    wait_ready(carousel["id"])
    published = call("POST", f"{ig_id}/media_publish", {"creation_id": carousel["id"]})

    # 게시 결과 확인: 3장인지, 캡션이 붙었는지
    media_id = published["id"]
    info = call("GET", media_id, {"fields": "permalink,caption,children{id}"})
    count = len(info.get("children", {}).get("data", []))
    (folder / "POSTED").write_text(info.get("permalink") or media_id, encoding="utf-8")
    print(f"{date}: 게시 완료 {info.get('permalink')} ({count}장)")
    if count != len(IMAGES) or not info.get("caption"):
        print(f"::error::게시됐지만 확인 필요: {count}장, 캡션 {'있음' if info.get('caption') else '없음'}")
        sys.exit(2)


if __name__ == "__main__":
    main()

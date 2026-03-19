import requests
from bs4 import BeautifulSoup
import json
import datetime
import os
import hashlib
import re
from urllib.parse import urljoin, urlparse, parse_qsl, urlencode, urlunparse

BASE_URL = "https://nanabunnonijyuuni-mobile.com/s/n110/media/list?dy={}"
SITE_ROOT = "https://nanabunnonijyuuni-mobile.com"


def _normalize_url(href: str) -> str:
    """
    规范化活动链接，去掉会导致同一活动链接不同但内容相同的参数，
    例如 ima / dy 等页面状态参数。
    """
    if not href:
        return ""

    full_url = href if href.startswith("http") else urljoin(SITE_ROOT, href)
    parsed = urlparse(full_url)

    filtered_query = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        if key.lower() not in {"ima", "dy"}:
            filtered_query.append((key, value))

    normalized_query = urlencode(filtered_query, doseq=True)

    normalized = urlunparse((
        parsed.scheme,
        parsed.netloc,
        parsed.path,
        parsed.params,
        normalized_query,
        ""
    ))
    return normalized


def _normalize_title(title: str) -> str:
    """
    智能归一化标题，用于模糊去重。
    尽量消除：
    - 全角/半角空格
    - 各种引号/括号差异
    - 连续空白
    - 末尾多余标点
    """
    if not title:
        return ""

    t = title.strip().lower()

    replacements = {
        "　": " ",
        "『": "",
        "』": "",
        "「": "",
        "」": "",
        "“": "",
        "”": "",
        "\"": "",
        "'": "",
        "（": "(",
        "）": ")",
        "【": "[",
        "】": "]",
        "～": "~",
        "−": "-",
        "—": "-",
        "―": "-",
        "‐": "-",
        "！": "!",
        "？": "?",
        "：": ":",
    }

    for old, new in replacements.items():
        t = t.replace(old, new)

    t = re.sub(r"\s+", "", t)
    t = re.sub(r"[!！?？。．、,，]+$", "", t)

    return t


def _normalize_category(category_text: str) -> str:
    """
    分类统一映射成前端用的英文分类。
    """
    if not category_text:
        return "Other"

    text = category_text.strip().lower()

    mapping = {
        "テレビ": "TV",
        "tv": "TV",
        "ラジオ": "Radio",
        "radio": "Radio",
        "web": "Web",
        "配信": "Web",
        "ライブ": "Live",
        "live": "Live",
        "イベント": "Event",
        "event": "Event",
        "特典会": "Event",
        "雑誌": "Release",
        "cd": "Release",
        "dvd": "Release",
        "cddvd": "Release",
        "その他": "Other",
        "other": "Other",
    }

    for key, value in mapping.items():
        if key == text:
            return value

    for key, value in mapping.items():
        if key in text:
            return value

    return "Other"


def _stable_event_id(date_str: str, title: str, category_text: str, href: str) -> str:
    normalized_url = _normalize_url(href)
    normalized_title = _normalize_title(title)
    normalized_category = _normalize_category(category_text)
    raw = f"{date_str}|{normalized_title}|{normalized_category}|{normalized_url}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def _normalize_date(raw_date: str, year_month: str) -> str:
    clean = raw_date.replace(".", "-").replace("/", "-").strip()
    parts = [p for p in clean.split("-") if p]

    if len(parts) == 2:
        year = year_month[:4]
        month, day = parts
    elif len(parts) == 3:
        year, month, day = parts
    else:
        year = year_month[:4]
        month = year_month[4:]
        day = "".join(filter(str.isdigit, raw_date))

    return f"{year}-{month.zfill(2)}-{day.zfill(2)}"


def _better_event(new_event: dict, old_event: dict) -> dict:
    """
    合并重复项时，优先保留信息更完整的一条。
    """
    if old_event is None:
        return new_event

    def score(e: dict) -> tuple:
        return (
            1 if e.get("url") else 0,
            1 if e.get("time") else 0,
            len(e.get("title", "")),
            len(e.get("url", "")),
        )

    return new_event if score(new_event) > score(old_event) else old_event


def _dedupe_events(events: list) -> list:
    """
    两层去重：
    1. 严格去重：日期 + 原标题 + 分类 + 规范化URL
    2. 智能去重：日期 + 归一化标题 + 分类
    """
    # 第一层：严格去重
    strict_map = {}

    for e in events:
        date_str = (e.get("date") or "").strip()
        title = (e.get("title") or "").strip()
        category = (e.get("category") or "").strip()
        normalized_url = _normalize_url(e.get("url", ""))

        strict_key = (
            date_str,
            title,
            category,
            normalized_url,
        )

        candidate = {
            **e,
            "url": normalized_url,
        }

        strict_map[strict_key] = _better_event(candidate, strict_map.get(strict_key))

    strict_events = list(strict_map.values())

    # 第二层：智能去重
    smart_map = {}

    for e in strict_events:
        date_str = (e.get("date") or "").strip()
        title = (e.get("title") or "").strip()
        category = (e.get("category") or "").strip()

        smart_key = (
            date_str,
            _normalize_title(title),
            category,
        )

        smart_map[smart_key] = _better_event(e, smart_map.get(smart_key))

    deduped = list(smart_map.values())

    # 重建稳定 id
    rebuilt = []
    for e in deduped:
        rebuilt.append({
            **e,
            "id": _stable_event_id(
                e.get("date", ""),
                e.get("title", ""),
                e.get("category", ""),
                e.get("url", ""),
            )
        })

    return rebuilt


def fetch_events_for_month(year_month: str) -> list:
    url = BASE_URL.format(year_month)
    print(f"正在获取: {url}")

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
        "Referer": "https://nanabunnonijyuuni-mobile.com/",
    }

    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
    except Exception as e:
        print(f"获取网页失败: {e}")
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    events = []

    media_boxes = soup.select("section.media_container div.media_box")
    print(f"{year_month} 找到日期块: {len(media_boxes)}")

    if not media_boxes:
        legacy_items = soup.select(".media_list li, .schedule_list li, article")
        print(f"{year_month} 回退旧结构，找到项目数: {len(legacy_items)}")

        for item in legacy_items:
            try:
                date_elem = item.find(class_=["date", "time", "day"])
                title_elem = item.find(class_=["title", "name", "txt"])
                category_elem = item.find(class_=["category", "tag", "label"])

                if not date_elem or not title_elem:
                    continue

                raw_date = date_elem.get_text(strip=True)
                title = title_elem.get_text(strip=True)
                category_text = category_elem.get_text(strip=True) if category_elem else ""
                clean_date = _normalize_date(raw_date, year_month)
                cat_en = _normalize_category(category_text)

                link_elem = item.find("a")
                href = ""
                detail_url = ""

                if link_elem and link_elem.has_attr("href"):
                    href = link_elem["href"]
                    detail_url = _normalize_url(href)

                events.append(
                    {
                        "id": _stable_event_id(clean_date, title, category_text, href),
                        "date": clean_date,
                        "title": title,
                        "category": cat_en,
                        "time": "",
                        "url": detail_url,
                    }
                )
            except Exception as e:
                print(f"解析旧结构时出错: {e}")

        events = _dedupe_events(events)
        print(f"{year_month} 抓取到活动数: {len(events)}")
        return events

    for box in media_boxes:
        try:
            year_div = box.find("div", class_="media_date_year")
            day_div = box.find("div", class_="media_date_day")

            if not year_div or not day_div:
                continue

            year = year_div.get_text(strip=True)
            month_day_raw = day_div.get_text(separator=" ", strip=True).split()[0]

            if "." in month_day_raw:
                month, day = month_day_raw.split(".", 1)
            elif "/" in month_day_raw:
                month, day = month_day_raw.split("/", 1)
            else:
                month = month_day_raw[:2]
                day = month_day_raw[2:]

            date_str = f"{year}-{month.zfill(2)}-{day.zfill(2)}"

            for link in box.find_all("a", class_="media_box_list"):
                try:
                    category_elem = link.find("div", class_="media_category")
                    title_elem = link.find("div", class_="media_title")

                    category_text = category_elem.get_text(strip=True) if category_elem else ""
                    title = title_elem.get_text(strip=True) if title_elem else ""

                    if not title:
                        continue

                    cat_en = _normalize_category(category_text)
                    href = link.get("href", "").strip()
                    detail_url = _normalize_url(href)

                    events.append(
                        {
                            "id": _stable_event_id(date_str, title, category_text, href),
                            "date": date_str,
                            "title": title,
                            "category": cat_en,
                            "time": "",
                            "url": detail_url,
                        }
                    )
                except Exception as e:
                    print(f"解析单个活动时出错: {e}")
        except Exception as e:
            print(f"解析日期块时出错: {e}")

    events = _dedupe_events(events)
    print(f"{year_month} 抓取到活动数: {len(events)}")
    return events


def main():
    all_events = []
    months_to_fetch = []
    now = datetime.datetime.now()

    is_fetch_all = os.environ.get("FETCH_ALL") == "true"

    if is_fetch_all:
        print("--- 执行全量抓取 (2018年至今) ---")
        start_year = 2018
        end_year = now.year + 1
        for year in range(start_year, end_year + 1):
            for month in range(1, 13):
                months_to_fetch.append(f"{year}{month:02d}")
    else:
        print("--- 执行日常增量抓取 (近两个月) ---")
        months_to_fetch.append(now.strftime("%Y%m"))
        months_to_fetch.append((now + datetime.timedelta(days=31)).strftime("%Y%m"))

    months_to_fetch = sorted(list(set(months_to_fetch)))
    print("本次抓取月份:", months_to_fetch)

    existing_events = []
    if not is_fetch_all and os.path.exists("events.json"):
        try:
            with open("events.json", "r", encoding="utf-8") as f:
                existing_events = json.load(f)
            print(f"读取旧 events.json 成功，已有 {len(existing_events)} 条")
        except Exception as e:
            print(f"读取旧 events.json 失败: {e}")

    for ym in months_to_fetch:
        month_events = fetch_events_for_month(ym)
        all_events.extend(month_events)

    if not is_fetch_all:
        merged_events = existing_events + all_events
    else:
        merged_events = all_events

    final_events = _dedupe_events(merged_events)
    final_events.sort(key=lambda x: (x["date"], x["title"]))

    with open("events.json", "w", encoding="utf-8") as f:
        json.dump(final_events, f, ensure_ascii=False, indent=2)

    print(f"成功更新 events.json，当前总共 {len(final_events)} 条数据")


if __name__ == "__main__":
    main()

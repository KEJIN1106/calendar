import requests
from bs4 import BeautifulSoup
import json
import datetime
import os
import hashlib

BASE_URL = "https://nanabunnonijyuuni-mobile.com/s/n110/media/list?dy={}"
SITE_ROOT = "https://nanabunnonijyuuni-mobile.com"


def _stable_event_id(date_str: str, title: str, category_text: str, href: str) -> str:
    raw = f"{date_str}|{title}|{category_text}|{href}"
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


def _map_category(category_text: str) -> str:
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
        "その他": "Other",
        "other": "Other",
    }

    for key, value in mapping.items():
        if key.lower() == text:
            return value

    for key, value in mapping.items():
        if key.lower() in text:
            return value

    return "Other"


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
                cat_en = _map_category(category_text)

                link_elem = item.find("a")
                href = ""
                detail_url = ""

                if link_elem and link_elem.has_attr("href"):
                    href = link_elem["href"]
                    detail_url = href if href.startswith("http") else f"{SITE_ROOT}{href}"

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

                    cat_en = _map_category(category_text)
                    href = link.get("href", "").strip()
                    detail_url = href if href.startswith("http") else (f"{SITE_ROOT}{href}" if href else "")

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
        events = fetch_events_for_month(ym)
        all_events.extend(events)

    if not is_fetch_all:
        events_dict = {e["id"]: e for e in existing_events}
        for e in all_events:
            events_dict[e["id"]] = e
        final_events = list(events_dict.values())
    else:
        dedup = {}
        for e in all_events:
            dedup[e["id"]] = e
        final_events = list(dedup.values())

    final_events.sort(key=lambda x: (x["date"], x["title"]))

    with open("events.json", "w", encoding="utf-8") as f:
        json.dump(final_events, f, ensure_ascii=False, indent=2)

    print(f"成功更新 events.json，当前总共 {len(final_events)} 条数据")


if __name__ == "__main__":
    main()

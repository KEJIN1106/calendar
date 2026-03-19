import requests
from bs4 import BeautifulSoup
import json
import datetime
import os
import hashlib
import re
from urllib.parse import urljoin, urlparse, parse_qsl, urlencode, urlunparse

SITE_ROOT_227 = "https://nanabunnonijyuuni-mobile.com"
BASE_URL_227 = "https://nanabunnonijyuuni-mobile.com/s/n110/media/list?dy={}"

SITE_ROOT_BD = "https://bang-dream.com"
BASE_URL_BD = "https://bang-dream.com/events?page={}"


# =========================
# Common helpers
# =========================

def _normalize_url(href: str, site_root: str = "") -> str:
    if not href:
        return ""

    full_url = href if href.startswith("http") else urljoin(site_root, href)
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


def _stable_event_id(project: str, date_str: str, title: str, category: str, href: str) -> str:
    normalized_url = _normalize_url(href)
    normalized_title = _normalize_title(title)
    raw = f"{project}|{date_str}|{normalized_title}|{category}|{normalized_url}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def _better_event(new_event: dict, old_event: dict) -> dict:
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
    strict_map = {}

    for e in events:
        date_str = (e.get("date") or "").strip()
        title = (e.get("title") or "").strip()
        category = (e.get("category") or "").strip()
        project = (e.get("project") or "").strip()
        normalized_url = _normalize_url(e.get("url", ""))

        strict_key = (
            project,
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

    smart_map = {}

    for e in strict_events:
        date_str = (e.get("date") or "").strip()
        title = (e.get("title") or "").strip()
        category = (e.get("category") or "").strip()
        project = (e.get("project") or "").strip()

        smart_key = (
            project,
            date_str,
            _normalize_title(title),
            category,
        )

        smart_map[smart_key] = _better_event(e, smart_map.get(smart_key))

    deduped = list(smart_map.values())

    rebuilt = []
    for e in deduped:
        rebuilt.append({
            **e,
            "id": _stable_event_id(
                e.get("project", ""),
                e.get("date", ""),
                e.get("title", ""),
                e.get("category", ""),
                e.get("url", ""),
            )
        })

    return rebuilt


def _normalize_227_date(raw_date: str, year_month: str) -> str:
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


def _map_227_category(category_text: str) -> str:
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


# =========================
# 22/7
# =========================

def fetch_227_events_for_month(year_month: str) -> list:
    url = BASE_URL_227.format(year_month)
    print(f"[22/7] 正在获取: {url}")

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
        "Referer": SITE_ROOT_227 + "/",
    }

    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
    except Exception as e:
        print(f"[22/7] 获取网页失败: {e}")
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    events = []

    media_boxes = soup.select("section.media_container div.media_box")
    print(f"[22/7] {year_month} 找到日期块: {len(media_boxes)}")

    if not media_boxes:
        legacy_items = soup.select(".media_list li, .schedule_list li, article")
        print(f"[22/7] {year_month} 回退旧结构，找到项目数: {len(legacy_items)}")

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
                clean_date = _normalize_227_date(raw_date, year_month)
                cat_en = _map_227_category(category_text)

                link_elem = item.find("a")
                href = link_elem["href"] if link_elem and link_elem.has_attr("href") else ""
                detail_url = _normalize_url(href, SITE_ROOT_227)

                events.append({
                    "id": _stable_event_id("22/7", clean_date, title, cat_en, href),
                    "date": clean_date,
                    "title": title,
                    "category": cat_en,
                    "time": "",
                    "url": detail_url,
                    "project": "22/7",
                    "source": "nanabunnonijyuuni-mobile.com",
                })
            except Exception as e:
                print(f"[22/7] 解析旧结构时出错: {e}")

        return _dedupe_events(events)

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

                    cat_en = _map_227_category(category_text)
                    href = link.get("href", "").strip()
                    detail_url = _normalize_url(href, SITE_ROOT_227)

                    events.append({
                        "id": _stable_event_id("22/7", date_str, title, cat_en, href),
                        "date": date_str,
                        "title": title,
                        "category": cat_en,
                        "time": "",
                        "url": detail_url,
                        "project": "22/7",
                        "source": "nanabunnonijyuuni-mobile.com",
                    })
                except Exception as e:
                    print(f"[22/7] 解析单个活动时出错: {e}")
        except Exception as e:
            print(f"[22/7] 解析日期块时出错: {e}")

    events = _dedupe_events(events)
    print(f"[22/7] {year_month} 抓取到活动数: {len(events)}")
    return events


# =========================
# BanG Dream!
# =========================

def _bd_date_candidates(date_text: str):
    """
    支持：
    2026年8月29日(土)・30日(日)
    2026年4月17日(金)、4月26日(日)、5月1日(金)
    2026年6月18日(木)・6月26日(金)
    """
    if not date_text:
        return []

    text = date_text.replace("開催日時", "").strip()
    text = text.replace("、", "・").replace("･", "・")

    parts = [p.strip() for p in text.split("・") if p.strip()]
    dates = []

    current_year = None
    current_month = None

    for part in parts:
        m = re.search(r'(?:(\d{4})年)?(?:(\d{1,2})月)?(\d{1,2})日', part)
        if not m:
            continue

        year, month, day = m.groups()

        if year:
            current_year = int(year)
        if month:
            current_month = int(month)

        if current_year is None or current_month is None:
            continue

        dates.append(f"{current_year:04d}-{current_month:02d}-{int(day):02d}")

    return dates


def _map_bd_category(category_text: str) -> str:
    text = (category_text or "").strip().lower()
    if text == "live":
        return "Live"
    if text == "event":
        return "Event"
    if text == "release":
        return "Release"
    if text == "store":
        return "Other"
    if text == "other":
        return "Other"
    return "Other"


def _parse_bang_dream_detail(detail_url: str, headers: dict) -> list:
    try:
        response = requests.get(detail_url, headers=headers, timeout=30)
        response.raise_for_status()
    except Exception as e:
        print(f"[BanG Dream!] 详情页获取失败: {detail_url} | {e}")
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    page_text = soup.get_text("\n", strip=True)
    compact_text = re.sub(r"\s+", " ", page_text)

    # 标题
    title = ""
    h1 = soup.find("h1")
    if h1:
        title = h1.get_text(" ", strip=True)

    if not title:
        og_title = soup.find("meta", attrs={"property": "og:title"})
        if og_title and og_title.get("content"):
            title = og_title["content"].split("|")[0].strip()

    if not title:
        print(f"[BanG Dream!] 详情页标题解析失败: {detail_url}")
        return []

    # 分类
    category = "Other"
    m_cat = re.search(r'^\s*(Live|Event|Release|Store|Other)\s*$', page_text, re.MULTILINE)
    if m_cat:
        category = _map_bd_category(m_cat.group(1).strip())

    # 日期：兼容 日程 / 開催日 / 開催日時
    raw_date_text = ""

    patterns = [
        r'(?:日程|開催日|開催日時)\s*[:：]?\s*(.{0,180})',
    ]

    for pat in patterns:
        m_date = re.search(pat, compact_text)
        if m_date:
            raw_date_text = m_date.group(1).strip()
            break

    if not raw_date_text:
        print(f"[BanG Dream!] 详情页日期解析失败: {detail_url}")
        return []

    # 在这些字段前截断，避免把后面说明吞进去
    raw_date_text = re.split(
        r'場所|会場|概要|出演|チケット|料金|開場|開演|お問い合わせ|主催|協賛',
        raw_date_text
    )[0].strip()

    dates = _bd_date_candidates(raw_date_text)
    if not dates:
        print(f"[BanG Dream!] 日期候选为空: {detail_url} | {raw_date_text}")
        return []

    events = []
    for date_str in dates:
        events.append({
            "id": _stable_event_id("BanG Dream!", date_str, title, category, detail_url),
            "date": date_str,
            "title": title,
            "category": category,
            "time": "",
            "url": detail_url,
            "project": "BanG Dream!",
            "source": "bang-dream.com",
        })

    return events


def fetch_bang_dream_events(max_pages: int = 12) -> list:
    print("[BanG Dream!] 开始抓取")
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
        "Referer": SITE_ROOT_BD + "/",
    }

    all_events = []
    seen_urls = set()

    for page in range(1, max_pages + 1):
        url = BASE_URL_BD.format(page)
        print(f"[BanG Dream!] 正在获取列表页: {url}")

        try:
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
        except Exception as e:
            print(f"[BanG Dream!] 第 {page} 页获取失败: {e}")
            continue

        print(f"[BanG Dream!] 第 {page} 页状态码: {response.status_code}")
        print(f"[BanG Dream!] 第 {page} 页实际地址: {response.url}")

        soup = BeautifulSoup(response.text, "html.parser")

        links = soup.select('a[href^="/events/"], a[href*="/events/"]')
        print(f"[BanG Dream!] 第 {page} 页候选链接数: {len(links)}")

        page_events_before = len(all_events)
        page_detail_urls = []

        for a in links:
            href = a.get("href", "").strip()
            if not href:
                continue

            full_url = _normalize_url(href, SITE_ROOT_BD)

            # 排除列表页、分页页
            if full_url.rstrip("/") == SITE_ROOT_BD + "/events":
                continue
            if "/events?page=" in full_url:
                continue
            if re.search(r"/events/page/\d+/?", full_url):
                continue

            if full_url in seen_urls:
                continue

            seen_urls.add(full_url)
            page_detail_urls.append(full_url)

        print(f"[BanG Dream!] 第 {page} 页详情链接数: {len(page_detail_urls)}")

        for detail_url in page_detail_urls:
            detail_events = _parse_bang_dream_detail(detail_url, headers)
            if detail_events:
                all_events.extend(detail_events)
                print(f"[BanG Dream!] 抓到: {detail_url} -> {len(detail_events)} 条")
            else:
                print(f"[BanG Dream!] 未抓到有效活动: {detail_url}")

        page_added = len(all_events) - page_events_before
        print(f"[BanG Dream!] 第 {page} 页新增活动数: {page_added}")

        if page > 3 and page_added == 0:
            break

    all_events = _dedupe_events(all_events)
    print(f"[BanG Dream!] 抓取完成，总活动数: {len(all_events)}")
    return all_events


# =========================
# Main
# =========================

def main():
    all_events = []
    months_to_fetch = []
    now = datetime.datetime.now()

    is_fetch_all = os.environ.get("FETCH_ALL") == "true"

    if is_fetch_all:
        print("--- 执行全量抓取 (22/7 2018年至今 + BanG Dream! 分页) ---")
        start_year = 2018
        end_year = now.year + 1
        for year in range(start_year, end_year + 1):
            for month in range(1, 13):
                months_to_fetch.append(f"{year}{month:02d}")
    else:
        print("--- 执行日常增量抓取 ---")
        months_to_fetch.append(now.strftime("%Y%m"))
        months_to_fetch.append((now + datetime.timedelta(days=31)).strftime("%Y%m"))

    months_to_fetch = sorted(list(set(months_to_fetch)))
    print("本次抓取 22/7 月份:", months_to_fetch)

    existing_events = []
    if not is_fetch_all and os.path.exists("events.json"):
        try:
            with open("events.json", "r", encoding="utf-8") as f:
                existing_events = json.load(f)
            print(f"读取旧 events.json 成功，已有 {len(existing_events)} 条")
        except Exception as e:
            print(f"读取旧 events.json 失败: {e}")

    # 22/7
    for ym in months_to_fetch:
        month_events = fetch_227_events_for_month(ym)
        all_events.extend(month_events)

    # BanG Dream!
    bd_events = fetch_bang_dream_events(max_pages=12)
    all_events.extend(bd_events)

    merged_events = existing_events + all_events if not is_fetch_all else all_events
    final_events = _dedupe_events(merged_events)
    final_events.sort(key=lambda x: (x["date"], x["project"], x["title"]))

    with open("events.json", "w", encoding="utf-8") as f:
        json.dump(final_events, f, ensure_ascii=False, indent=2)

    print(f"成功更新 events.json，当前总共 {len(final_events)} 条数据")


if __name__ == "__main__":
    main()

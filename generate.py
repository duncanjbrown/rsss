#!/usr/bin/env python3
import yaml
import feedparser
import sys
import os
from datetime import datetime, timezone
from email.utils import formatdate
from zoneinfo import ZoneInfo
from xml.sax.saxutils import escape


def entry_date(entry):
    for attr in ("published_parsed", "updated_parsed"):
        t = getattr(entry, attr, None)
        if t:
            return datetime(*t[:6], tzinfo=timezone.utc)
    return datetime.min.replace(tzinfo=timezone.utc)


def entry_content(e):
    # Prefer full content over summary so embedded images are included
    content_list = getattr(e, "content", None)
    if content_list:
        return content_list[0].get("value", "")
    return getattr(e, "summary", getattr(e, "description", ""))


def entry_enclosures(e):
    lines = []
    for enc in getattr(e, "enclosures", []):
        url = enc.get("url", "")
        mime = enc.get("type", "")
        length = enc.get("length", "0")
        if url:
            lines.append(
                f'      <enclosure url="{escape(url)}" type="{escape(mime)}" length="{length}"/>'
            )
    return "\n".join(lines)


def build_rss(title, description, link, entries):
    items = []
    for e in entries:
        pub_date_str = formatdate(entry_date(e).timestamp())
        item_title = escape(getattr(e, "title", "(no title)"))
        item_link = getattr(e, "link", "")
        item_desc = entry_content(e)
        item_guid = escape(getattr(e, "id", item_link))
        enclosures = entry_enclosures(e)

        item = (
            f"    <item>\n"
            f"      <title>{item_title}</title>\n"
            f"      <link>{escape(item_link)}</link>\n"
            f"      <description><![CDATA[{item_desc}]]></description>\n"
            f"      <pubDate>{pub_date_str}</pubDate>\n"
            f"      <guid>{item_guid}</guid>\n"
        )
        if enclosures:
            item += enclosures + "\n"
        item += "    </item>"
        items.append(item)

    now = formatdate()
    body = "\n".join(items)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0">\n'
        "  <channel>\n"
        f"    <title>{escape(title)}</title>\n"
        f"    <description>{escape(description)}</description>\n"
        f"    <link>{escape(link)}</link>\n"
        f"    <lastBuildDate>{now}</lastBuildDate>\n"
        f"{body}\n"
        "  </channel>\n"
        "</rss>\n"
    )


def build_index(feeds):
    links = "\n".join(
        f'    <li><a href="{fid}/">{escape(cfg["title"])}</a>'
        f" — {escape(cfg.get('description', ''))}</li>"
        for fid, cfg in feeds.items()
    )
    london = ZoneInfo("Europe/London")
    now = datetime.now(london).strftime("%Y-%m-%d %H:%M %Z")
    return (
        "<!DOCTYPE html>\n<html>\n<head><meta charset=utf-8>"
        "<title>RSSs</title></head>\n<body>\n"
        "<h1>RSSs</h1>\n<ul>\n"
        f"{links}\n"
        "</ul>\n"
        f"<p>Last refreshed: {now}</p>\n"
        "</body>\n</html>\n"
    )


def github_pages_url():
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if not repo:
        return ""
    owner, name = repo.split("/", 1)
    return f"https://{owner}.github.io/{name}/"


def generate(config_path, output_dir):
    with open(config_path) as f:
        config = yaml.safe_load(f)

    os.makedirs(output_dir, exist_ok=True)
    base_url = github_pages_url()

    for feed_id, feed_cfg in config.items():
        title = feed_cfg["title"]
        description = feed_cfg.get("description", "")
        feed_url = f"{base_url}{feed_id}/" if base_url else ""
        link = feed_cfg.get("link", feed_url)
        source_urls = feed_cfg["feeds"]

        all_entries = []
        for url in source_urls:
            print(f"  fetching {url}")
            parsed = feedparser.parse(url, resolve_relative_uris=False)
            if parsed.bozo and not parsed.entries:
                print(f"  warning: failed to parse {url}: {parsed.bozo_exception}")
            all_entries.extend(parsed.entries)

        all_entries.sort(key=entry_date, reverse=True)

        rss = build_rss(title, description, link, all_entries)
        feed_dir = os.path.join(output_dir, feed_id)
        os.makedirs(feed_dir, exist_ok=True)
        out_path = os.path.join(feed_dir, "index.xml")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(rss)
        print(f"  wrote {out_path} ({len(all_entries)} entries)")

    index_path = os.path.join(output_dir, "index.html")
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(build_index(config))
    print(f"  wrote {index_path}")


if __name__ == "__main__":
    config_path = sys.argv[1] if len(sys.argv) > 1 else "config.yaml"
    output_dir = sys.argv[2] if len(sys.argv) > 2 else "public"
    print(f"Generating feeds from {config_path} into {output_dir}/")
    generate(config_path, output_dir)
    print("Done.")

#!/usr/bin/env python3
import yaml
import feedparser
import sys
import os
from datetime import datetime, timezone
from email.utils import formatdate
from zoneinfo import ZoneInfo
from xml.sax.saxutils import escape


FEED_XSL = """\
<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform">
  <xsl:output method="html" encoding="UTF-8" doctype-system="about:legacy-compat"/>
  <xsl:template name="pub-date">
    <xsl:param name="d"/>
    <xsl:variable name="after-weekday" select="substring-after($d, ', ')"/>
    <xsl:variable name="day" select="substring-before($after-weekday, ' ')"/>
    <xsl:variable name="after-day" select="substring-after($after-weekday, ' ')"/>
    <xsl:variable name="month" select="substring-before($after-day, ' ')"/>
    <xsl:variable name="after-month" select="substring-after($after-day, ' ')"/>
    <xsl:variable name="year" select="substring-before($after-month, ' ')"/>
    <xsl:value-of select="concat($day, ' ', $month, ' ', $year)"/>
  </xsl:template>
  <xsl:template match="/">
    <html lang="en">
      <head>
        <meta charset="UTF-8"/>
        <meta name="viewport" content="width=device-width, initial-scale=1"/>
        <title><xsl:value-of select="/rss/channel/title"/></title>
        <style>
          *, *::before, *::after { box-sizing: border-box; }
          body {
            font-family: system-ui, sans-serif;
            background: #fff;
            color: #000;
            margin: 0;
            padding: 0;
          }
          header {
            border-bottom: 1px solid #000;
            padding: 1.5rem 1rem 1rem;
          }
          header h1 { margin: 0 0 0.25rem; font-size: 1.25rem; }
          header p { margin: 0; font-size: 0.875rem; color: #666; }
          header a { color: inherit; }
          main {
            max-width: 720px;
            padding: 0 1rem 3rem;
          }
          article {
            border-bottom: 1px solid #ddd;
            padding: 1rem 0;
          }
          article:last-child { border-bottom: none; }
          h2 { margin: 0 0 0.25rem; font-size: 1rem; font-weight: 600; }
          h2 a { color: #000; text-decoration: none; }
          h2 a:hover { text-decoration: underline; }
          .meta { font-size: 0.75rem; color: #888; margin-bottom: 0.5rem; }
          .meta a { color: #888; }
          .content { font-size: 0.9rem; line-height: 1.6; color: #111; }
          .content img { max-width: 100%; height: auto; display: block; margin: 0.5rem 0; }
          .content p:first-child { margin-top: 0; }
          .content p:last-child { margin-bottom: 0; }
        </style>
      </head>
      <body>
        <header>
          <h1>
            <xsl:choose>
              <xsl:when test="/rss/channel/link != ''">
                <a href="{/rss/channel/link}"><xsl:value-of select="/rss/channel/title"/></a>
              </xsl:when>
              <xsl:otherwise><xsl:value-of select="/rss/channel/title"/></xsl:otherwise>
            </xsl:choose>
          </h1>
          <p><xsl:value-of select="/rss/channel/description"/></p>
        </header>
        <main>
          <xsl:for-each select="/rss/channel/item">
            <article>
              <h2>
                <xsl:choose>
                  <xsl:when test="link != ''">
                    <a href="{link}"><xsl:value-of select="title"/></a>
                  </xsl:when>
                  <xsl:otherwise><xsl:value-of select="title"/></xsl:otherwise>
                </xsl:choose>
              </h2>
              <div class="meta">
                <xsl:call-template name="pub-date">
                  <xsl:with-param name="d" select="pubDate"/>
                </xsl:call-template>
                <xsl:if test="source != ''">
                  <xsl:text> · </xsl:text>
                  <a href="{source/@url}"><xsl:value-of select="source"/></a>
                </xsl:if>
              </div>
              <div class="content">
                <xsl:attribute name="data-html">
                  <xsl:value-of select="description"/>
                </xsl:attribute>
              </div>
            </article>
          </xsl:for-each>
        </main>
        <script>
          document.querySelectorAll('[data-html]').forEach(function(el) {
            el.innerHTML = el.getAttribute('data-html');
          });
        </script>
      </body>
    </html>
  </xsl:template>
</xsl:stylesheet>
"""


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

        source_title = e.get("_source_title", "")
        source_url = e.get("_source_url", "")
        author = e.get("author", "")
        byline = f'<p><small><em>From <a href="{source_url}">{source_title}</a></em></small></p>'
        item = (
            f"    <item>\n"
            f"      <title>{item_title}</title>\n"
            f"      <link>{escape(item_link)}</link>\n"
            f"      <description><![CDATA[{byline}{item_desc}]]></description>\n"
            f"      <pubDate>{pub_date_str}</pubDate>\n"
            f"      <guid>{item_guid}</guid>\n"
            f'      <source url="{escape(source_url)}">{escape(source_title)}</source>\n'
        )
        if author:
            item += f"      <author><![CDATA[{author}]]></author>\n"
        if enclosures:
            item += enclosures + "\n"
        item += "    </item>"
        items.append(item)

    now = formatdate()
    body = "\n".join(items)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<?xml-stylesheet type="text/xsl" href="../feed.xsl"?>\n'
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
        f'    <li><a href="{fid}/index.xml">{escape(cfg["title"])}</a>'
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
            source_title = parsed.feed.get("title", url)
            for entry in parsed.entries:
                entry["_source_title"] = source_title
                entry["_source_url"] = url
            all_entries.extend(parsed.entries)

        all_entries.sort(key=entry_date, reverse=True)

        rss = build_rss(title, description, link, all_entries)
        feed_dir = os.path.join(output_dir, feed_id)
        os.makedirs(feed_dir, exist_ok=True)
        out_path = os.path.join(feed_dir, "index.xml")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(rss)
        print(f"  wrote {out_path} ({len(all_entries)} entries)")

    xsl_path = os.path.join(output_dir, "feed.xsl")
    with open(xsl_path, "w", encoding="utf-8") as f:
        f.write(FEED_XSL)
    print(f"  wrote {xsl_path}")

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

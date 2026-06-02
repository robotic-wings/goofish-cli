"""item list — 查看当前账号的在售商品。

调 mtop.idle.web.xyh.item.list v1.0，返回结构化数据。
"""
from __future__ import annotations

from typing import Any

from goofish_cli.core import Session, Strategy, command
from goofish_cli.core.mtop import call

MAX_LIMIT = 100
DEFAULT_PAGE_SIZE = 20


def _normalize_limit(value: Any) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return DEFAULT_PAGE_SIZE
    return min(MAX_LIMIT, max(1, n))


def _item_id_from_url(url: str) -> str:
    import re

    m = re.search(r"[?&]id=(\d+)", url or "")
    return m.group(1) if m else ""


STATUS_MAP = {"0": "在售", "1": "已下架"}


def _extract_item(card_data: dict[str, Any]) -> dict[str, Any]:
    """从 cardData 提取商品关键字段。"""
    item_id = str(card_data.get("id", ""))
    title = card_data.get("title", "")
    # priceInfo: {"preText": "¥", "price": "1999"}
    price_info = card_data.get("priceInfo") or {}
    price = (price_info.get("preText") or "") + str(price_info.get("price") or "")
    status_code = str(card_data.get("itemStatus", ""))
    status = STATUS_MAP.get(status_code, status_code)
    # picInfo: {"picUrl": "https://..."}
    pic_info = card_data.get("picInfo") or {}
    image_url = pic_info.get("picUrl", "")
    # itemLabelDataVO 标签：labelData → r3/r2/... → tagList → data.content
    labels = []
    label_vo = card_data.get("itemLabelDataVO") or {}
    if isinstance(label_vo, dict):
        label_data = label_vo.get("labelData") or {}
        for _region, region_data in label_data.items():
            for tag in (region_data.get("tagList") if isinstance(region_data, dict) else []) or []:
                tag_data = tag.get("data") if isinstance(tag, dict) else None
                if isinstance(tag_data, dict) and tag_data.get("content"):
                    labels.append(tag_data["content"])
    return {
        "item_id": item_id,
        "title": title,
        "price": price,
        "status": status,
        "image_url": image_url,
        "tags": labels,
    }


@command(
    namespace="item",
    name="list",
    description="查看当前账号的在售商品（API 直签）",
    strategy=Strategy.COOKIE,
    columns=["rank", "item_id", "title", "price", "status"],
)
def list_items(limit: int = 50) -> dict[str, Any]:
    session = Session.load()
    n = _normalize_limit(limit)

    items: list[dict[str, Any]] = []
    page_number = 1

    while len(items) < n:
        raw = call(
            session,
            api="mtop.idle.web.xyh.item.list",
            data={
                "needGroupInfo": True,
                "pageNumber": page_number,
                "userId": session.unb,
                "pageSize": DEFAULT_PAGE_SIZE,
            },
            version="1.0",
            spm_cnt="a21ybx.item.0.0",
        )
        data = raw.get("data", {}) or {}

        # 置顶商品（仅首页）
        if page_number == 1:
            top = data.get("topItem")
            if top and isinstance(top, dict):
                top_data = top.get("cardData") or top
                item = _extract_item(top_data)
                if item["item_id"]:
                    items.append(item)

        # 普通列表
        for card in data.get("cardList") or []:
            card_data = card.get("cardData") or card
            item = _extract_item(card_data)
            if item["item_id"]:
                items.append(item)

        if not data.get("nextPage"):
            break
        page_number += 1

    items = items[:n]

    for i, it in enumerate(items):
        it["rank"] = i + 1

    return {"items": items, "total": len(items)}


__test__ = {
    "_normalize_limit": _normalize_limit,
    "_item_id_from_url": _item_id_from_url,
    "_extract_item": _extract_item,
}

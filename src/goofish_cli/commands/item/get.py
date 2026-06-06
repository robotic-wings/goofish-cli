"""item get — 查询商品详情。接口 mtop.taobao.idle.pc.detail v1.0（只读）"""

from typing import Any

from goofish_cli.core import Session, Strategy, command
from goofish_cli.core.mtop import call


@command(
    namespace="item",
    name="get",
    description="查询闲鱼商品详情（只读）",
    strategy=Strategy.COOKIE,
    columns=["item_id", "title", "price", "seller_nick", "status"],
)
def get(item_id: str) -> dict[str, Any]:
    session = Session.load()
    raw = call(
        session,
        api="mtop.taobao.idle.pc.detail",
        data={"itemId": str(item_id)},
        version="1.0",
        spm_cnt="a21ybx.item.0.0",
    )
    data = raw.get("data", {}) or {}
    # mtop.taobao.idle.pc.detail 把字段拆到 itemDO / sellerDO；trackParams 只剩埋点
    # 用的 id 列表，不含 title/price/nick，所以早期从 trackParams 取会全空。
    item = data.get("itemDO", {}) or {}
    seller = data.get("sellerDO", {}) or {}
    return {
        "item_id": str(item.get("itemId") or item_id),
        "title": item.get("title", ""),
        "price": item.get("soldPrice", item.get("originalPrice", "")),
        "seller_nick": seller.get("nick", ""),
        "status": item.get("itemStatusStr", ""),
        "raw": raw,
    }

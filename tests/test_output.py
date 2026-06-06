"""output._as_rows —— 表格行抽取。重点回归：列表型命令把行包在 dict 里
（{"items": [...], "total": N}）时，表格要渲染内层 list，而不是把整个 dict
当成一行（那样声明的列在顶层取不到，会全空）。"""
from goofish_cli.core.output import _as_rows


def test_wrapper_dict_unwraps_inner_list():
    data = {"items": [{"item_id": "1", "title": "a"}], "total": 1}
    cols, rows = _as_rows(data, columns=["item_id", "title"])
    assert rows == [{"item_id": "1", "title": "a"}]
    assert "item_id" in cols and "title" in cols


def test_wrapper_dict_picks_list_matching_columns():
    data = {"meta": [{"x": 1}], "sessions": [{"session_id": "s1"}]}
    _, rows = _as_rows(data, columns=["session_id"])
    assert rows == [{"session_id": "s1"}]


def test_flat_dict_is_single_row():
    # item get / location default 等扁平 dict：当作一行，不受内层 dict 字段影响
    data = {"item_id": "1", "title": "x", "raw": {"nested": "dict"}}
    cols, rows = _as_rows(data)
    assert rows == [data]
    assert cols == ["item_id", "title", "raw"]


def test_empty_list_value_does_not_trigger_unwrap():
    # location default 的 all=[] 是空 list，不应被当成行来源
    data = {"prov": "浙江", "all": []}
    _, rows = _as_rows(data)
    assert rows == [data]


def test_list_of_dicts_passthrough():
    data = [{"a": 1}, {"a": 2, "b": 3}]
    cols, rows = _as_rows(data)
    assert rows == data
    assert cols == ["a", "b"]


def test_scalar_returns_empty():
    assert _as_rows("hi") == ([], [])

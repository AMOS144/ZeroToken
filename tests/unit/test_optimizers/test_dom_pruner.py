"""DOM 智能剪枝测试"""


def test_removes_script_style_tags():
    from zerotoken.optimizers.dom_pruner import prune_dom

    html = """<html><head><style>.x{}</style><script>var a=1;</script></head>
    <body><div id="main"><p>Hello</p></div></body></html>"""
    result = prune_dom(html)
    assert "<script" not in result
    assert "<style" not in result
    assert "Hello" in result
    assert 'id="main"' in result


def test_removes_svg_noscript():
    from zerotoken.optimizers.dom_pruner import prune_dom

    html = """<body><svg width="100" height="100"><circle/></svg>
    <noscript>Enable JS</noscript><p>Content</p></body>"""
    result = prune_dom(html)
    assert "<svg" not in result
    assert "<noscript" not in result
    assert "Content" in result


def test_removes_decoration_attrs():
    from zerotoken.optimizers.dom_pruner import prune_dom

    html = '<div class="css-1a2b3c sc-abc" style="color:red" data-v-abc="1" id="keep" role="button">OK</div>'
    result = prune_dom(html)
    assert 'id="keep"' in result
    assert 'role="button"' in result
    assert "style=" not in result
    assert "data-v-" not in result


def test_preserves_semantic_attrs():
    from zerotoken.optimizers.dom_pruner import prune_dom

    html = '<input id="user" name="username" aria-label="Username" placeholder="Enter name" type="text" value="test">'
    result = prune_dom(html)
    assert 'name="username"' in result
    assert 'aria-label="Username"' in result
    assert 'placeholder="Enter name"' in result
    assert 'type="text"' in result


def test_truncates_long_list():
    from zerotoken.optimizers.dom_pruner import prune_dom

    items = "".join(f"<li>Item {i}</li>" for i in range(50))
    html = f"<ul>{items}</ul>"
    result = prune_dom(html, max_list_items=5)
    assert "Item 0" in result
    assert "Item 4" in result
    assert "Item 49" not in result
    assert "50" in result


def test_max_depth_truncation():
    from zerotoken.optimizers.dom_pruner import prune_dom

    html = "<div>" * 15 + "<p>Deep</p>" + "</div>" * 15
    result = prune_dom(html, max_depth=10)
    assert "[...]" in result

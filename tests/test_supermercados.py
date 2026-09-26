from supermercados.base import StoreError, normalize_unit, parse_unit_price_text, to_float
from supermercados.compare import basket_summary, search_all, sort_products
from supermercados.demo import demo_search
from supermercados.stores import Carrefour, Consum, Dia, Mercadona
from supermercados.base import Product


def test_to_float():
    assert to_float("1,25 €") == 1.25
    assert to_float("1.25") == 1.25
    assert to_float("1.234,50") == 1234.5
    assert to_float(2) == 2.0
    assert to_float(None) is None
    assert to_float("n/d") is None


def test_normalize_unit():
    assert normalize_unit("L", 1.0) == (1.0, "l")
    assert normalize_unit("kg", 3.2) == (3.2, "kg")
    assert normalize_unit("LITRE", 0.9) == (0.9, "l")
    assert normalize_unit("1 Litro", 0.9) == (0.9, "l")
    assert normalize_unit("100 g", 0.5) == (5.0, "kg")
    assert normalize_unit("docena", 2.4) == (0.2, "ud")
    assert normalize_unit("raro", 1.0) == (1.0, None)


def test_parse_unit_price_text():
    assert parse_unit_price_text("1,05 €/l") == (1.05, "l")
    assert parse_unit_price_text("(3,20 €/Kg)") == (3.2, "kg")
    assert parse_unit_price_text(None) == (None, None)


def test_mercadona_parse():
    hit = {
        "display_name": "Leche entera Hacendado",
        "packaging": "Brick",
        "thumbnail": "https://img/1.jpg",
        "share_url": "https://tienda.mercadona.es/product/1",
        "price_instructions": {"unit_price": "0.97", "reference_price": "0.970", "reference_format": "L"},
    }
    p = Mercadona().parse_hit(hit)
    assert p.price == 0.97 and p.unit == "l" and p.unit_price == 0.97
    assert p.name == "Leche entera Hacendado (Brick)"


def test_dia_parse():
    item = {
        "display_name": "Leche entera Dia",
        "url": "/leche/p/123",
        "image": "/product_images/123.jpg",
        "prices": {"price": 0.92, "price_per_unit": 0.92, "measure_unit": "LITRE"},
    }
    p = Dia().parse_item(item)
    assert p.price == 0.92 and p.unit == "l"
    assert p.url == "https://www.dia.es/leche/p/123"


def test_consum_parse_prefers_offer():
    item = {
        "productData": {"name": "Leche entera", "brand": {"name": "Consum"}, "url": "https://x"},
        "priceData": {
            "prices": [
                {"id": "PRICE", "value": {"centAmount": 1.0, "centUnitAmount": 1.0}},
                {"id": "OFFER_PRICE", "value": {"centAmount": 0.8, "centUnitAmount": 0.8}},
            ],
            "unitPriceUnitType": "1 Litro",
        },
    }
    p = Consum().parse_item(item)
    assert p.price == 0.8 and p.unit == "l" and p.brand == "Consum"


def test_carrefour_parse():
    doc = {"display_name": "Leche", "active_price": 1.05, "price_per_unit_text": "1,05 €/l", "url": "/p/1"}
    p = Carrefour().parse_doc(doc)
    assert p.price == 1.05 and p.unit_price == 1.05 and p.unit == "l"
    assert p.url == "https://www.carrefour.es/p/1"


def test_parsers_skip_items_without_price():
    assert Mercadona().parse_hit({"display_name": "x"}) is None
    assert Dia().parse_item({"display_name": "x"}) is None
    assert Consum().parse_item({}) is None
    assert Carrefour().parse_doc({}) is None


def _p(store, name, price, unit_price, unit="l"):
    return Product(store=store, name=name, price=price, unit_price=unit_price, unit=unit)


def test_sort_by_unit_price_vs_price():
    products = [
        _p("A", "leche pack 6", 5.4, 0.9),
        _p("B", "leche 1 L", 1.0, 1.0),
        _p("C", "leche sin unidad", 0.5, None, None),
    ]
    assert [p.store for p in sort_products(products, True)] == ["A", "B", "C"]
    assert [p.store for p in sort_products(products, False)] == ["C", "B", "A"]


def test_search_all_handles_errors_and_filters():
    def fake(store, query):
        if store == "Roto":
            raise StoreError("Roto: 403")
        return [_p(store, "Leche entera", 1.0, 1.0), _p(store, "Galletas", 2.0, 2.0, "kg")]

    [res] = search_all(["leche"], ["A", "Roto"], fake)
    assert res.errors == {"Roto": "Roto: 403"}
    assert [p.name for p in res.products] == ["Leche entera"]


def test_basket_summary_with_demo():
    # search_all acepta también textos sueltos
    queries = ["leche entera", "huevos", "producto inexistente"]
    stores = ["Mercadona", "Dia"]
    results = search_all(queries, stores, lambda s, q: demo_search(s, q))
    summary = basket_summary(results)
    rows = summary["rows"]
    assert list(rows["Artículo"]) == queries
    assert rows.iloc[2]["Producto"] == "No encontrado"
    assert set(summary["totals"]) == set(stores)
    assert summary["missing"] == {"Mercadona": 1, "Dia": 1}
    assert summary["mixed_total"] <= min(summary["totals"].values())


# --- Calidades ---------------------------------------------------------------
from supermercados import quality
from supermercados.compare import Item
from supermercados.stores import Alcampo, Eroski


def test_quality_detection():
    assert quality.detect("Huevos camperos clase L") == ["campero"]
    assert quality.detect("Huevos de gallinas criadas en libertad") == ["campero"]
    assert "eco" in quality.detect("Arroz redondo ecológico")
    assert "eco" in quality.detect("Leche BIO")
    assert set(quality.detect("Arroz bomba D.O. Calasparra")) == {"bomba", "do"}
    assert quality.detect("Aceite de oliva virgen extra") == ["virgen_extra"]
    assert quality.detect("Doritos") == []


def test_eco_eggs_count_as_campero():
    assert quality.satisfies(["eco"], ["campero"])
    assert not quality.satisfies(["suelo"], ["campero"])
    assert not quality.satisfies(["campero"], ["eco"])
    assert quality.satisfies(["eco", "integral"], ["eco", "integral"])


def test_search_queries_adds_quality_terms():
    assert quality.search_queries("arroz", []) == ["arroz"]
    assert quality.search_queries("arroz", ["eco"]) == ["arroz", "arroz ecologico"]
    assert quality.search_queries("arroz ecológico", ["eco"]) == ["arroz ecológico"]


def test_search_all_filters_by_quality_and_dedupes():
    calls = []

    def fake(store, query):
        calls.append(query)
        return [
            _p(store, "Huevos gallinas suelo", 2.0, 0.17, "ud"),
            _p(store, "Huevos camperos", 2.8, 0.23, "ud"),
            _p(store, "Huevos ecológicos", 3.9, 0.33, "ud"),
        ]

    [res] = search_all([Item("huevos", 2, ["campero"])], ["A"], fake)
    assert sorted(calls) == ["huevos", "huevos campero"]
    assert [p.name for p in res.products] == ["Huevos camperos", "Huevos ecológicos"]
    assert res.discarded_quality == 1
    summary = basket_summary([res])
    assert summary["totals"] == {"A": 5.6}  # 2 docenas de camperos


def test_eco_basket_demo():
    items = [Item(q, 1, ["eco"]) for q in ("leche entera", "arroz", "huevos")]
    results = search_all(items, ["Mercadona", "Eroski"], lambda s, q: demo_search(s, q))
    for r in results:
        assert r.products and all("eco" in p.tags for p in r.products)


# --- Alcampo / Eroski ----------------------------------------------------------


def test_alcampo_generic_json():
    data = {
        "entities": {
            "product": {
                "abc": {
                    "name": "Leche entera ecológica AUCHAN 1 l",
                    "brand": "AUCHAN",
                    "price": {"amount": "1.29", "currency": "EUR"},
                    "unitPrice": {"price": {"amount": "1.29"}, "unit": "fop.price.per.litre"},
                    "image": {"src": "https://img/a.jpg"},
                }
            }
        }
    }

    class FakeAlcampo(Alcampo):
        def _get_json(self, url, **kwargs):
            return data

    [p] = FakeAlcampo().search("leche")
    assert (p.price, p.unit_price, p.unit) == (1.29, 1.29, "l")
    assert "eco" in p.tags and p.image == "https://img/a.jpg"


def test_alcampo_reports_errors_when_all_endpoints_fail():
    class Broken(Alcampo):
        def _get_json(self, url, **kwargs):
            raise StoreError("Alcampo: 403")

        def _get_html(self, url, **kwargs):
            raise StoreError("Alcampo: 403")

    try:
        Broken().search("leche")
    except StoreError as exc:
        assert "403" in str(exc)
    else:
        raise AssertionError("debería fallar")


def test_eroski_html_cards():
    html = """
    <div class="product-item">
      <h2 class="product-title"><a href="/es/productdetail/123-huevos">Huevos camperos Eroski, 12 uds</a></h2>
      <img src="https://img/h.jpg">
      <span class="price-offer-now">3,15 €</span>
      <span class="price-product">0,26 €/ud</span>
    </div>
    <div class="product-item">
      <h2 class="product-title"><a href="/es/productdetail/124">Arroz bomba</a></h2>
      <span class="price-offer-now">2,99 €</span>
      <span>2,99 €/kg</span>
    </div>"""
    products = Eroski().parse_html(html)
    assert [(p.name, p.price, p.unit_price, p.unit) for p in products] == [
        ("Huevos camperos Eroski, 12 uds", 3.15, 0.26, "ud"),
        ("Arroz bomba", 2.99, 2.99, "kg"),
    ]
    assert products[0].url == "https://supermercado.eroski.es/es/productdetail/123-huevos"
    assert products[0].tags == ["campero"]


def test_eroski_json_ld():
    html = """<script type="application/ld+json">
    {"@type": "ItemList", "itemListElement": [
      {"@type": "Product", "name": "Leche entera", "offers": {"price": "0.95", "priceCurrency": "EUR"}}
    ]}</script>"""
    [p] = Eroski().parse_html(html)
    assert (p.name, p.price) == ("Leche entera", 0.95)
